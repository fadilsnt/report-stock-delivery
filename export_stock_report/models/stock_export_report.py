from odoo import models, api
from collections import defaultdict
import time
import re
import random


class ReportExportStock(models.AbstractModel):
    _name = 'report.export_stock_report.report_export_stock'
    _description = 'Report Export Stock'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env['export.stock.wizard'].browse(docids)

        # ===== Domain picking =====
        domain = [
            ('picking_type_code', '=', 'outgoing'),
            ('scheduled_date', '>=', wizard.start_date),
            ('scheduled_date', '<=', wizard.end_date),
            ('picking_type_id.warehouse_id', 'in',
             wizard.warehouse_ids.ids or self.env['stock.warehouse'].search([]).ids),
            ('state', 'not in', ['draft', 'cancel'])
        ]

        pickings = self.env['stock.picking'].search(domain)

        # ===== Struktur hasil utama (TIDAK DIUBAH) =====
        results = defaultdict(
            lambda: defaultdict(
                lambda: defaultdict(
                    lambda: defaultdict(lambda: {"box": 0, "cont": 0, "grade": None})
                )
            )
        )

        warehouses = set()
        products = set()
        grades = set()

        colors = ["#d97c7c", "#7c9bd9", "#7cd99b", "#d9b37c", "#9e7cd9"]
        bg_color = random.choice(colors)

        grand_totals = {"box": 0, "cont": 0}
        warehouse_totals = defaultdict(lambda: {"box": 0, "cont": 0})

        # ===== Loop picking & move line =====
        for picking in pickings:
            wh_name = picking.picking_type_id.warehouse_id.name
            warehouses.add(wh_name)

            for ml in picking.move_line_ids:

                # ==================================================
                # FILTER OWNER SESUAI WIZARD SALES PERSON
                # ==================================================
                if wizard.sales_person_ids:
                    if not ml.owner_id or ml.owner_id.id not in wizard.sales_person_ids.ids:
                        continue

                # ===== Sales person dari OWNER (STRUKTUR TETAP) =====
                salesperson = ml.owner_id.name if ml.owner_id else "No Owner"

                # customer TETAP partner picking (XML AMAN)
                customer = picking.partner_id.name

                categ_name = (ml.product_id.categ_id.name or "").lower()
                if wizard.kategori_selection == "export" and categ_name != "export":
                    continue
                elif wizard.kategori_selection == "lokal" and categ_name != "lokal":
                    continue

                prod = ml.product_id.display_name
                products.add(prod)
                pr_name = ml.product_id.name

                # ===== Grade dari nama produk =====
                match = re.search(r'\((.*?)\)', prod)
                grade_from_display_name = match.group(1) if match else None
                if grade_from_display_name:
                    grades.add(grade_from_display_name)

                qty = ml.quantity

                box = qty
                cont_capacity = self._get_cont_capacity(ml.product_id)
                cont = qty / cont_capacity if cont_capacity else 0

                # ===== Simpan ke results (TIDAK DIUBAH) =====
                results[salesperson][customer][prod][wh_name]["box"] += box
                results[salesperson][customer][prod][wh_name]["cont"] += cont
                results[salesperson][customer][prod][wh_name]["grade"] = grade_from_display_name
                results[salesperson][customer][prod][wh_name]["name_product"] = pr_name

                warehouse_totals[wh_name]["box"] += box
                warehouse_totals[wh_name]["cont"] += cont

                grand_totals["box"] += box
                grand_totals["cont"] += cont

        # ===== Konversi per UoM BOX (TIDAK DIUBAH) =====
        uoms = self.env['uom.uom'].search(
            [('category_id.name', '=', 'BOX')],
            order="factor ASC"
        )

        warehouse_uom_totals = defaultdict(lambda: defaultdict(float))
        grand_uom_totals = defaultdict(float)

        for wh_name in warehouses:
            qty_box = warehouse_totals[wh_name]["box"]

            warehouse_uom_totals[wh_name]['total_count'] += qty_box
            grand_uom_totals['total_count'] += qty_box

            for uom in uoms:
                converted_qty = qty_box / uom.factor if uom.factor else 0
                warehouse_uom_totals[wh_name][uom.id] += converted_qty
                grand_uom_totals[uom.id] += converted_qty

        return {
            "doc_ids": docids,
            "doc_model": "export.stock.report.wizard",
            "docs": wizard,
            "results": results,
            "warehouses": sorted(list(warehouses)),
            "products": sorted(list(products)),
            "grades": sorted(list(grades)),
            "time": time,
            "bg_color": bg_color,
            "grand_totals": grand_totals,
            "warehouse_totals": warehouse_totals,
            "uoms": [{"id": u.id, "name": u.name, "factor": u.factor} for u in uoms],
            "warehouse_uom_totals": warehouse_uom_totals,
            "grand_uom_totals": grand_uom_totals,
        }

    def _get_cont_capacity(self, product):
        cont_attr = product.product_template_attribute_value_ids.filtered(
            lambda v: 'cont' in v.attribute_id.name.lower()
        )
        if cont_attr:
            try:
                return float(cont_attr[0].name)
            except Exception:
                return 0
        return 0
