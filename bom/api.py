
import json

import frappe
from frappe import _
from frappe.utils import cint, flt


@frappe.whitelist()
def get_production_order_data(bom_no):
    """Fetch Sales Order FG items and cumulative RM items from a Custom Production BOM."""

    bom = frappe.get_doc("BOM", bom_no)
    bom.check_permission("read")

    if not cint(bom.get("custom_custom_production_bom")):
        frappe.throw(_("This is not a Custom Production BOM."))

    if bom.docstatus != 1:
        frappe.throw(_("Please submit the BOM before creating Work Orders."))

    if not bom.custom_sales_order:
        frappe.throw(_("Please select a Sales Order in the BOM."))

    so = frappe.get_doc("Sales Order", bom.custom_sales_order)
    so.check_permission("read")

    if so.docstatus != 1:
        frappe.throw(_("The linked Sales Order must be submitted."))

    if so.company != bom.company:
        frappe.throw(_("The Sales Order and BOM must belong to the same Company."))

    fg_items = []

    for row in so.items:
        fg_items.append({
            "sales_order_item": row.name,
            "item_code": row.item_code,
            "item_name": row.item_name,
            "uom": row.uom,
            "stock_uom": row.stock_uom,
            "ordered_qty": flt(row.qty),
            "produced_qty": flt(row.produced_qty),
            "work_order_qty": flt(row.work_order_qty),
        })

    raw_materials = []

    for row in bom.items:
        raw_materials.append({
            "bom_item": row.name,
            "item_code": row.item_code,
            "item_name": row.item_name,
            "description": row.description,
            "uom": row.uom,
            "stock_uom": row.stock_uom,
            "master_qty": flt(row.qty),
            "stock_qty": flt(row.stock_qty),
            "source_warehouse": row.source_warehouse,
            "operation": row.operation,
            "rate": flt(row.rate),
        })

    return {
        "bom_no": bom.name,
        "sales_order": so.name,
        "customer": so.customer,
        "company": so.company,
        "project": bom.project or so.project,
        "fg_items": fg_items,
        "raw_materials": raw_materials,
    }


@frappe.whitelist()
def create_production_work_orders(bom_no, production_data):
    """
    Create one standard BOM and one draft standard Work Order
    for each selected Sales Order FG item.

    RM consumption quantities are entered per one FG unit.
    """

    if isinstance(production_data, str):
        production_data = json.loads(production_data)

    if not isinstance(production_data, list) or not production_data:
        frappe.throw(_("Please select at least one FG item."))

    master_bom = frappe.get_doc("BOM", bom_no)
    master_bom.check_permission("read")

    if not cint(master_bom.get("custom_custom_production_bom")):
        frappe.throw(_("This is not a Custom Production BOM."))

    if master_bom.docstatus != 1:
        frappe.throw(_("The Custom Production BOM must be submitted."))

    if not master_bom.custom_sales_order:
        frappe.throw(_("Please select a Sales Order in the Custom Production BOM."))

    so = frappe.get_doc("Sales Order", master_bom.custom_sales_order)
    so.check_permission("read")

    if so.docstatus != 1:
        frappe.throw(_("The linked Sales Order must be submitted."))

    if so.company != master_bom.company:
        frappe.throw(_("The Sales Order and BOM must belong to the same Company."))

    # Map Sales Order rows by their exact child-row names.
    so_items = {row.name: row for row in so.items}

    # Map master BOM RM rows by their exact child-row names.
    master_rm = {row.name: row for row in master_bom.items}

    selected_so_rows = set()
    created_records = []

    operation_fields = [
        "operation",
        "workstation_type",
        "workstation",
        "time_in_mins",
        "fixed_time",
        "hour_rate",
        "batch_size",
        "set_cost_based_on_bom_qty",
        "description",
    ]

    for fg_data in production_data:

        so_item_name = fg_data.get("sales_order_item")
        production_qty = flt(fg_data.get("qty"))

        if so_item_name not in so_items:
            frappe.throw(_("Invalid Sales Order Item selected."))

        if so_item_name in selected_so_rows:
            frappe.throw(_("The same Sales Order Item cannot be selected twice."))

        selected_so_rows.add(so_item_name)

        so_row = so_items[so_item_name]

        if production_qty <= 0:
            frappe.throw(
                _("Production quantity must be greater than zero for {0}.").format(
                    so_row.item_code
                )
            )

        remaining_qty = (
            flt(so_row.qty)
            - flt(so_row.produced_qty)
            - flt(so_row.work_order_qty)
        )

        if production_qty > remaining_qty:
            frappe.throw(
                _("Production quantity for {0} cannot exceed the remaining Sales Order quantity {1}.").format(
                    so_row.item_code, remaining_qty
                )
            )

        item_code = so_row.item_code

        # Get the Target Warehouse from the Sales Order Item.
        target_warehouse = so_row.warehouse

        if not target_warehouse:
            frappe.throw(
                _("Target Warehouse is missing for Sales Order Item {0} ({1}).").format(
                    so_item_name, item_code
                )
            )

        item_stock_uom = frappe.db.get_value(
            "Item", item_code, "stock_uom"
        )

        if not item_stock_uom:
            frappe.throw(
                _("Stock UOM is missing for Item {0}.").format(item_code)
            )

        # Create a separate standard BOM for this FG.
        generated_bom = frappe.new_doc("BOM")

        generated_bom.item = item_code
        generated_bom.company = master_bom.company
        generated_bom.quantity = 1
        generated_bom.uom = item_stock_uom
        generated_bom.is_active = 1
        generated_bom.is_default = 0
        generated_bom.project = master_bom.project or so.project

        generated_bom.with_operations = cint(
            master_bom.with_operations
        )

        generated_bom.transfer_material_against = (
            master_bom.transfer_material_against
        )

        generated_bom.allow_alternative_item = cint(
            master_bom.allow_alternative_item
        )

        generated_bom.rm_cost_as_per = master_bom.rm_cost_as_per
        generated_bom.currency = master_bom.currency
        generated_bom.conversion_rate = master_bom.conversion_rate or 1

        generated_bom.custom_source_production_bom = master_bom.name

        # Generated BOM must be a normal standard BOM.
        generated_bom.custom_custom_production_bom = 0

        # Add only the RM rows with positive per-unit consumption.
        fg_raw_materials = fg_data.get("raw_materials") or []

        if not fg_raw_materials:
            frappe.throw(
                _("Please enter RM consumption for {0}.").format(item_code)
            )

        used_rm_rows = set()

        for rm_data in fg_raw_materials:

            source_rm_name = rm_data.get("bom_item")
            consumption_qty = flt(rm_data.get("qty"))

            if source_rm_name not in master_rm:
                frappe.throw(_("Invalid Raw Material selected."))

            if source_rm_name in used_rm_rows:
                frappe.throw(
                    _("A Raw Material row cannot be entered twice for {0}.").format(
                        item_code
                    )
                )

            used_rm_rows.add(source_rm_name)

            if consumption_qty < 0:
                frappe.throw(_("RM consumption cannot be negative."))

            # Zero means this RM is not used for this FG.
            if consumption_qty == 0:
                continue

            source_rm = master_rm[source_rm_name]

            generated_bom.append("items", {
                "item_code": source_rm.item_code,
                "item_name": source_rm.item_name,
                "description": source_rm.description,
                "qty": consumption_qty,
                "uom": source_rm.uom,
                "source_warehouse": source_rm.source_warehouse,
                "operation": source_rm.operation,
                "allow_alternative_item": source_rm.allow_alternative_item,
                "do_not_explode": source_rm.do_not_explode,
                "include_item_in_manufacturing": (
                    source_rm.include_item_in_manufacturing
                ),
                "sourced_by_supplier": source_rm.sourced_by_supplier,
            })

        if not generated_bom.items:
            frappe.throw(
                _("At least one RM must have a positive consumption quantity for {0}.").format(
                    item_code
                )
            )

        # Copy operations from the Custom Production BOM.
        if generated_bom.with_operations:
            for source_operation in master_bom.operations:
                operation_data = {}

                for field in operation_fields:
                    if source_operation.get(field) is not None:
                        operation_data[field] = source_operation.get(field)

                generated_bom.append("operations", operation_data)

        # Insert and submit the FG-specific standard BOM.
        generated_bom.insert()
        generated_bom.submit()

        # Use ERPNext's standard Work Order creation method.
        from erpnext.manufacturing.doctype.work_order.work_order import (
            make_work_order,
        )

        wo_doc = make_work_order(
            bom_no=generated_bom.name,
            item=item_code,
            qty=production_qty,
            company=so.company,
            project=master_bom.project or so.project,
            use_multi_level_bom=0,
        )

        # Set the finished goods Target Warehouse.
        wo_doc.fg_warehouse = target_warehouse

        # Link Work Order to the exact Sales Order item row.
        wo_doc.sales_order = so.name
        wo_doc.custom_so_item = so_item_name
        wo_doc.custom_source_production_bom = master_bom.name

        # Save as Draft; do not submit automatically.
        wo_doc.insert()

        created_records.append({
            "item_code": item_code,
            "sales_order_item": so_item_name,
            "generated_bom": generated_bom.name,
            "work_order": wo_doc.name,
            "qty": production_qty,
        })

    return {
        "message": _("Production Work Orders created successfully."),
        "created_records": created_records,
    }
