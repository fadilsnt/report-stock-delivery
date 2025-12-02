from odoo import models, api
from collections import defaultdict
import time
import re
import random


class ReportStockWarehouse(models.AbstractModel):
    _name = 'report.export_stock_report.stock_report_template'
    _description = 'Stock Report by Warehouse'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env['stock.report.wizard'].browse(docids)

        # ===== Domain picking =====
        domain = [
            ('picking_type_code', '=', 'incoming'),
            ('scheduled_date', '<=', wizard.end_date),
            ('picking_type_id.warehouse_id', 'in',
             wizard.warehouse_ids.ids or self.env['stock.warehouse'].search([]).ids),
            ('person_ids', 'in',
             wizard.sales_person_ids.ids or self.env['res.users'].search([]).ids),
            ('state', 'not in', ['draft', 'cancel'])
        ]

        pickings = self.env['stock.picking'].search(domain)

        # ===== Struktur hasil utama =====
        results = defaultdict(
            lambda: defaultdict(
                lambda: defaultdict(
                    lambda: defaultdict(lambda: {"box": 0, "cont": 0, "grade": None, "name_product": None})
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
        # ===== change here: customer_totals per warehouse + total =====
        customer_totals = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {"box": 0, "cont": 0})))

        # ===== Loop picking & move line =====
        seen_quant = set()  # untuk menghindari double counting per (product, owner, warehouse)
        for picking in pickings:
            salesperson = picking.person_ids.name or "-"
            # NOTE: jangan langsung gunakan picking.owner_id di sini — owner sebenarnya per move_line
            wh = picking.picking_type_id.warehouse_id
            wh_name = wh.name
            warehouses.add(wh_name)

            for ml in picking.move_line_ids:
                # kategori filter tetap sama
                categ_name = (ml.product_id.categ_id.name or "").lower()
                if wizard.kategori_selection == "export" and categ_name != "export":
                    continue
                elif wizard.kategori_selection == "lokal" and categ_name != "lokal":
                    continue

                prod = ml.product_id.display_name
                products.add(prod)
                pr_name = ml.product_id.name

                # Ambil grade dari nama produk (misal Product (A))
                # match = re.search(r'\((.*?)\)', prod)
                # grade_from_display_name = match.group(1) if match else None
                grade_from_display_name = self._get_grade(ml.product_id)
                if grade_from_display_name:
                    grades.add(grade_from_display_name)

                # Tentukan owner yang benar: prioritas ml.owner_id, lalu picking.owner_id, lalu partner
                owner = ml.owner_id or picking.owner_id or picking.partner_id
                owner_id = owner.id if owner else False
                # gunakan owner name untuk grouping customer
                customer = owner.name if owner and owner.name else (picking.partner_id.name or "Unknown Customer")

                # key untuk mencegah hitungan berulang sama (product, owner, warehouse)
                seen_key = (ml.product_id.id, owner_id, wh.id)
                if seen_key in seen_quant:
                    # sudah dihitung quant untuk kombinasi ini => skip
                    continue
                seen_quant.add(seen_key)

                quant_domain = [
                    ('product_id', '=', ml.product_id.id),
                    ('location_id', 'child_of', wh.view_location_id.id),
                    ('owner_id', '=', owner_id)
                ]
                qty_onhand = sum(self.env['stock.quant'].search(quant_domain).mapped('quantity')) if owner_id else sum(self.env['stock.quant'].search([
                    ('product_id', '=', ml.product_id.id),
                    ('location_id', 'child_of', wh.view_location_id.id),
                ]).mapped('quantity'))
                qty = qty_onhand

                box = qty
                # cont = qty / ml.product_id.container_capacity if ml.product_id.container_capacity else 0
                cont_capacity = self._get_cont_capacity(ml.product_id)
                cont = qty / cont_capacity if cont_capacity else 0

                # Simpan ke results
                data_dict = results[salesperson][customer][prod][wh_name]
                data_dict["box"] += box
                data_dict["cont"] += cont
                data_dict["grade"] = grade_from_display_name
                data_dict["name_product"] = pr_name

                # Total per warehouse
                warehouse_totals[wh_name]["box"] += box
                warehouse_totals[wh_name]["cont"] += cont

                # === customer_totals: per warehouse ===
                customer_totals[salesperson][customer][wh_name]["box"] += box
                customer_totals[salesperson][customer][wh_name]["cont"] += cont
                # and accumulate total under key "total"
                customer_totals[salesperson][customer]["total"]["box"] += box
                customer_totals[salesperson][customer]["total"]["cont"] += cont

                # Total global
                grand_totals["box"] += box
                grand_totals["cont"] += cont

        # ===== Hitung total per produk (per warehouse & total) =====
        product_group_totals = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {"box": 0, "cont": 0})))
        for sp, custs in results.items():
            for cust, prods in custs.items():
                for prod_name, wh_data in prods.items():
                    base_name = re.sub(r'\s*\(.*?\)', '', prod_name).strip()
                    for wh_name, vals in wh_data.items():
                        product_group_totals[cust][base_name][wh_name]["box"] += vals.get("box", 0)
                        product_group_totals[cust][base_name][wh_name]["cont"] += vals.get("cont", 0)
                        product_group_totals[cust][base_name]["total"]["box"] += vals.get("box", 0)
                        product_group_totals[cust][base_name]["total"]["cont"] += vals.get("cont", 0)
        # ===== Tambahan UoM BOX =====
        # uoms = self.env['uom.uom'].search([('category_id.name', '=', 'BOX')], order="factor ASC")
        # warehouse_uom_totals = defaultdict(lambda: defaultdict(float))
        # grand_uom_totals = defaultdict(float)

        # for wh_name in warehouses:
        #     qty_box = warehouse_totals[wh_name]["box"]
        #     warehouse_uom_totals[wh_name]['total_count'] += qty_box
        #     grand_uom_totals['total_count'] += qty_box

        #     for uom in uoms:
        #         converted_qty = qty_box / uom.factor if uom.factor else 0
        #         warehouse_uom_totals[wh_name][uom.id] += converted_qty
        #         grand_uom_totals[uom.id] += converted_qty

        uoms = self.env['uom.uom'].search([('category_id.name', '=', 'BOX')], order="factor ASC")
        warehouse_uom_totals = defaultdict(lambda: defaultdict(float))
        grand_uom_totals = defaultdict(float)

        warehouse_uom_totals_count = defaultdict(lambda: defaultdict(float))
        grand_uom_totals_count = defaultdict(float)

        for wh_name in warehouses:
            qty_box = warehouse_totals[wh_name]["box"]
            qty_cont = warehouse_totals[wh_name]["cont"]

            # === versi dari BOX ===
            warehouse_uom_totals[wh_name]['total_count'] += qty_box
            grand_uom_totals['total_count'] += qty_box

            for uom in uoms:
                converted_qty = qty_box / uom.factor if uom.factor else 0
                warehouse_uom_totals[wh_name][uom.id] += converted_qty
                grand_uom_totals[uom.id] += converted_qty

            # === versi dari COUNT ===
            warehouse_uom_totals_count[wh_name]['total_count'] += qty_cont
            grand_uom_totals_count['total_count'] += qty_cont

            for uom in uoms:
                converted_qty_count = qty_cont / uom.factor if uom.factor else 0
                warehouse_uom_totals_count[wh_name][uom.id] += converted_qty_count
                grand_uom_totals_count[uom.id] += converted_qty_count

        # ===== TOTAL PER UoM PER WAREHOUSE (pivot) =====
        total_per_uom_warehouse = defaultdict(
            lambda: defaultdict(
                lambda: defaultdict(lambda: defaultdict(float))
            )
        )
        # Struktur: total_per_uom_warehouse[uom_name][product][warehouse]['converted']

        for uom in uoms:
            uom_name = uom.name
            uom_factor = uom.factor or 1

            for sp, custs in results.items():
                for cust, prods in custs.items():
                    for prod_name, wh_data in prods.items():
                        match = re.search(r'\((.*?)\)', prod_name)
                        grade = match.group(1) if match else None

                        for wh_name, vals in wh_data.items():
                            qty_box = vals.get("box", 0)
                            converted = qty_box / uom_factor if uom_factor else 0
                            total_per_uom_warehouse[uom_name][prod_name][wh_name]['converted'] += converted
                            total_per_uom_warehouse[uom_name][prod_name][wh_name]['grade'] = grade

        # ======== Tambahan baru: TOTAL KESELURUHAN PER WAREHOUSE (BARU) ========
        stock_domain = [
            ('date', '<=', wizard.end_date),
            ('state', 'not in', ['draft', 'cancel']),
            # ('location_dest_id.warehouse_id', 'in', wizard.warehouse_ids.ids),
        ]
        move_lines = self.env['stock.move.line'].search(stock_domain)

        total_warehouse_summary_new = defaultdict(lambda: defaultdict(float))
        grand_total_summary_new = defaultdict(float)
        all_uoms_new = set()

        for line in move_lines:
            wh = line.location_dest_id.warehouse_id
            if not wh:
                continue
            wh_name = wh.name
            uom_name = line.product_uom_id.name or 'Unknown'

            total_warehouse_summary_new[wh_name][uom_name] += line.quantity
            total_warehouse_summary_new[wh_name]['Total Count (BOX)'] += line.quantity
            total_warehouse_summary_new[wh_name]['CONT'] += line.quantity / 3100
            all_uoms_new.add(uom_name)

        # === Hitung GRAND TOTAL ===
        for wh_data in total_warehouse_summary_new.values():
            for uom_name, qty in wh_data.items():
                grand_total_summary_new[uom_name] += qty

        total_warehouse_summary_new['GRAND TOTAL'] = grand_total_summary_new
        total_warehouse_summary_new = dict(sorted(total_warehouse_summary_new.items(), key=lambda x: x[0].lower()))

        # === UoM yang muncul di data saja ===
        uoms_used_new = [{'name': name} for name in sorted(all_uoms_new)]

        # ====== Tambahan: Hitung Total per Salesperson ======
        salesperson_totals = defaultdict(lambda: defaultdict(lambda: {"box": 0, "cont": 0}))

        for sp, custs in customer_totals.items():
            for cust_name, whs in custs.items():
                # akumulasi per warehouse dari customer_totals
                for wh_name, vals in whs.items():
                    if wh_name == 'total':
                        continue
                    salesperson_totals[sp][wh_name]["box"] += vals.get("box", 0)
                    salesperson_totals[sp][wh_name]["cont"] += vals.get("cont", 0)

                # total keseluruhan per salesperson
                salesperson_totals[sp]["total"]["box"] += whs.get("total", {}).get("box", 0)
                salesperson_totals[sp]["total"]["cont"] += whs.get("total", {}).get("cont", 0)

        # ====== Tambahan baru: Grand Total per Warehouse ======
        grand_totals_per_wh = defaultdict(lambda: {"box": 0, "cont": 0})
        grand_totals_per_wh["total"] = {"box": 0, "cont": 0}

        for sp, custs in customer_totals.items():
            for cust_name, whs in custs.items():
                for wh_name, vals in whs.items():
                    if wh_name == "total":
                        continue
                    grand_totals_per_wh[wh_name]["box"] += vals.get("box", 0)
                    grand_totals_per_wh[wh_name]["cont"] += vals.get("cont", 0)
                    # Total keseluruhan semua warehouse
                    grand_totals_per_wh["total"]["box"] += vals.get("box", 0)
                    grand_totals_per_wh["total"]["cont"] += vals.get("cont", 0)

        if wizard.warehouse_ids:
            ordered_warehouses = wizard.warehouse_ids.mapped('name')
        else:
            ordered_warehouses = sorted(list(warehouses))

        return {
            "doc_ids": docids,
            "doc_model": "stock.report.wizard",
            "docs": wizard,
            "results": results,
            "warehouses": ordered_warehouses,
            "products": sorted(list(products)),
            "grades": sorted(list(grades)),
            "time": time,
            "bg_color": bg_color,
            "grand_totals": grand_totals,
            "warehouse_totals": warehouse_totals,
            "customer_totals": customer_totals,
            "uoms": [{"id": u.id, "name": u.name, "factor": u.factor} for u in uoms],
            "warehouse_uom_totals": warehouse_uom_totals,
            "grand_uom_totals": grand_uom_totals,
            "grand_uom_totals_count" : grand_uom_totals_count,
            "product_group_totals": product_group_totals,
            "uoms_new": uoms_used_new,
            "total_warehouse_summary_new": total_warehouse_summary_new,
            "salesperson_totals": salesperson_totals,
            "grand_totals_per_wh": grand_totals_per_wh,


        }
    
    def _get_cont_capacity(self, product):
        cont_attr = product.product_template_attribute_value_ids.filtered(
            lambda v: 'cont' in v.attribute_id.name.lower()
        )
        if cont_attr:
            try:
                return float(cont_attr[0].name)
            except:
                return 0
        return 0
    
    def _get_grade(self, product):
        grade_attr = product.product_template_attribute_value_ids.filtered(
            lambda v: 'grade' in v.attribute_id.name.lower()
        )
        if grade_attr:
            return grade_attr[0].name
        return None


