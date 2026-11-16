
frappe.ui.form.on("BOM", {
    refresh(frm) {
        update_bom_fields(frm);

        if (frm.doc.docstatus === 1 &&
            cint(frm.doc.custom_custom_production_bom)) {

            // Remove ERPNext's standard button and add our own action.
            frm.page.remove_inner_button(__("Work Order"), __("Create"));

            frm.add_custom_button(__("Work Order"), () => {
                open_custom_production_dialog(frm);
            }, __("Create"));
        }
    },

    custom_custom_production_bom(frm) {
        update_bom_fields(frm);
    }
});


function update_bom_fields(frm) {
    const is_custom = cint(frm.doc.custom_custom_production_bom) === 1;

    frm.set_df_property("item", "reqd", is_custom ? 0 : 1);
    frm.toggle_reqd("item", !is_custom);

    frm.set_df_property("quantity", "reqd", 1);
    frm.toggle_reqd("quantity", true);

    frm.refresh_field("item");
    frm.refresh_field("quantity");
}


// Fetch Sales Order FG and master BOM RM data.
function open_custom_production_dialog(frm) {
    frappe.call({
        method: "bom.api.get_production_order_data",
        args: {
            bom_no: frm.doc.name
        },
        freeze: true,
        freeze_message: __("Loading production data..."),
        callback(r) {
            if (r.message) {
                show_combined_production_dialog(frm, r.message);
            }
        }
    });
}


function show_combined_production_dialog(frm, data) {
    let dialog;

    const fields = [];

    data.fg_items.forEach((fg, index) => {
        const remaining = flt(
            fg.ordered_qty - fg.produced_qty - fg.work_order_qty
        );

        const rm_field = `rm_select_${index}`;
        const html_field = `rm_qty_html_${index}`;

        fields.push({
            fieldtype: "Section Break",
            label: `${fg.item_code} - ${fg.item_name}`
        });

        fields.push({
            fieldtype: "Check",
            fieldname: `select_fg_${index}`,
            label: "Select Finished Good"
        });

        fields.push({
            fieldtype: "Float",
            fieldname: `fg_qty_${index}`,
            label: `Production Quantity (${fg.stock_uom || fg.uom})`,
            default: 0
        });

        fields.push({
            fieldtype: "Data",
            fieldname: `remaining_${index}`,
            label: "Remaining Sales Order Quantity",
            default: remaining,
            read_only: 1
        });

        fields.push({
            fieldtype: "MultiSelectList",
            fieldname: rm_field,
            label: `Select Raw Materials for ${fg.item_code}`,
            get_data(txt) {
                const search = (txt || "").toLowerCase();

                return data.raw_materials
                    .filter(rm => {
                        const value =
                            `${rm.item_code} ${rm.item_name || ""}`.toLowerCase();

                        return value.includes(search);
                    })
                    .map(rm => ({
                        value: rm.bom_item,
                        description: `${rm.item_code} - ${rm.item_name || ""}`
                    }));
            },
            onchange() {
                render_selected_rm(dialog, data, index);
            }
        });

        fields.push({
            fieldtype: "HTML",
            fieldname: html_field
        });
    });

    dialog = new frappe.ui.Dialog({
        title: __("Create Production Work Orders"),
        size: "extra-large",
        fields,

        primary_action_label: __("Create Work Orders"),

        primary_action(values) {
            const selected = [];
            let has_error = false;

            data.fg_items.forEach((fg, index) => {
                if (!values[`select_fg_${index}`]) {
                    return;
                }

                const qty = flt(values[`fg_qty_${index}`]);
                const remaining = flt(
                    fg.ordered_qty - fg.produced_qty - fg.work_order_qty
                );

                if (qty <= 0 || qty > remaining) {
                    frappe.msgprint(
                        __("Enter a valid production quantity for {0}. Remaining quantity: {1}", [
                            fg.item_code, remaining
                        ])
                    );
                    has_error = true;
                    return;
                }

                const selected_rm = values[`rm_select_${index}`] || [];

                if (!selected_rm.length) {
                    frappe.msgprint(
                        __("Select at least one Raw Material for {0}.", [
                            fg.item_code
                        ])
                    );
                    has_error = true;
                    return;
                }

                const wrapper = dialog.fields_dict[
                    `rm_qty_html_${index}`
                ].$wrapper;

                const raw_materials = [];

                selected_rm.forEach(rm_name => {
                    const input = wrapper.find(
                        `[data-bom-item="${rm_name}"]`
                    );

                    const consumption = flt(input.val());

                    if (consumption <= 0) {
                        frappe.msgprint(
                            __("Enter a positive RM consumption quantity for {0}.", [
                                rm_name
                            ])
                        );
                        has_error = true;
                        return;
                    }

                    raw_materials.push({
                        bom_item: rm_name,
                        qty: consumption
                    });
                });

                selected.push({
                    sales_order_item: fg.sales_order_item,
                    item_code: fg.item_code,
                    qty: qty,
                    raw_materials: raw_materials
                });
            });

            if (has_error) return;

            if (!selected.length) {
                frappe.msgprint(__("Please select at least one FG item."));
                return;
            }

            dialog.hide();
            create_custom_work_orders(frm, selected);
        }
    });

    dialog.show();
}


// Display quantity inputs only for the selected RM items.
function render_selected_rm(dialog, data, fg_index) {
    const fieldname = `rm_select_${fg_index}`;
    const html_field = `rm_qty_html_${fg_index}`;

    const selected = dialog.get_value(fieldname) || [];
    const wrapper = dialog.fields_dict[html_field].$wrapper;

    if (!selected.length) {
        wrapper.html(
            `<p class="text-muted">${__("Select Raw Materials to enter consumption quantities.")}</p>`
        );
        return;
    }

    let html = `
        <div class="table-responsive">
            <table class="table table-bordered">
                <thead>
                    <tr>
                        <th>${__("Raw Material")}</th>
                        <th>${__("Unit")}</th>
                        <th>${__("Consumption per one FG")}</th>
                    </tr>
                </thead>
                <tbody>
    `;

    selected.forEach(rm_name => {
        const rm = data.raw_materials.find(
            row => row.bom_item === rm_name
        );

        if (!rm) return;

        html += `
            <tr>
                <td>
                    ${frappe.utils.escape_html(rm.item_code)}
                    - ${frappe.utils.escape_html(rm.item_name || "")}
                </td>
                <td>${frappe.utils.escape_html(rm.uom || rm.stock_uom || "")}</td>
                <td>
                    <input
                        type="number"
                        min="0"
                        step="any"
                        class="form-control"
                        data-bom-item="${frappe.utils.escape_html(rm.bom_item)}"
                        placeholder="${__("Enter quantity per FG")}"
                    >
                </td>
            </tr>
        `;
    });

    html += `
                </tbody>
            </table>
        </div>
    `;

    wrapper.html(html);
}


// Create generated standard BOMs and draft Work Orders.
function create_custom_work_orders(frm, selected) {
    frappe.call({
        method: "bom.api.create_production_work_orders",
        args: {
            bom_no: frm.doc.name,
            production_data: JSON.stringify(selected)
        },
        freeze: true,
        freeze_message: __("Creating BOMs and Draft Work Orders..."),

        callback(r) {
            if (!r.message) return;

            const records = r.message.created_records || [];

            let html = `
                <p>${__("Production documents created successfully.")}</p>
                <table class="table table-bordered">
                    <thead>
                        <tr>
                            <th>${__("Finished Good")}</th>
                            <th>${__("Quantity")}</th>
                            <th>${__("Generated BOM")}</th>
                            <th>${__("Draft Work Order")}</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            records.forEach(record => {
                html += `
                    <tr>
                        <td>${frappe.utils.escape_html(record.item_code)}</td>
                        <td>${record.qty}</td>
                        <td>
                            <a href="/app/bom/${encodeURIComponent(record.generated_bom)}">
                                ${frappe.utils.escape_html(record.generated_bom)}
                            </a>
                        </td>
                        <td>
                            <a href="/app/work-order/${encodeURIComponent(record.work_order)}">
                                ${frappe.utils.escape_html(record.work_order)}
                            </a>
                        </td>
                    </tr>
                `;
            });

            html += "</tbody></table>";

            frappe.msgprint({
                title: __("Production Created"),
                indicator: "green",
                message: html
            });

            frm.reload_doc();
        }
    });
}
