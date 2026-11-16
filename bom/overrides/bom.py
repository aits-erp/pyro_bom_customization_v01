
import frappe
from frappe import _
from frappe.utils import cint

from erpnext.manufacturing.doctype.bom.bom import BOM


class CustomBOM(BOM):

    def is_custom_production_bom(self):
        return cint(self.get("custom_custom_production_bom")) == 1

    def autoname(self):
        if not self.is_custom_production_bom():
            return super().autoname()

        prefix = "BOM-CUSTOM"
        existing = frappe.db.sql(
            """
            SELECT name FROM `tabBOM`
            WHERE name LIKE %s
            ORDER BY name DESC
            """,
            (prefix + "-%",),
            as_dict=True,
        )

        index = len(existing) + 1
        name = f"{prefix}-{index:05d}"

        while frappe.db.exists("BOM", name):
            index += 1
            name = f"{prefix}-{index:05d}"

        self.name = name

    def validate_main_item(self):
        if not self.is_custom_production_bom():
            return super().validate_main_item()

        # Custom Production BOM does not require an FG Item.
        self.item = None
        self.item_name = None
        self.description = None
        self.uom = None

        if not self.quantity or self.quantity <= 0:
            frappe.throw(_("Quantity should be greater than 0"))

    def manage_default_bom(self):
        if self.is_custom_production_bom():
            self.db_set("is_default", 0)
            return

        return super().manage_default_bom()

    def check_recursion(self):
        if self.is_custom_production_bom():
            # Keep the standard recursion checks for child BOMs,
            # but do not compare against a missing parent FG Item.
            original_item = self.item
            try:
                self.item = None
                return super().check_recursion()
            finally:
                self.item = original_item

        return super().check_recursion()

    def validate_scrap_items(self):
        if self.is_custom_production_bom() and not self.uom:
            if self.process_loss_percentage and self.process_loss_percentage > 100:
                frappe.throw(_("Process Loss Percentage cannot be greater than 100"))
            return

        return super().validate_scrap_items()
