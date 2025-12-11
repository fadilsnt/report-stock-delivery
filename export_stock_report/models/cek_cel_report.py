from odoo import models, api
from collections import defaultdict

class ReportCekCL(models.AbstractModel):
    _name = 'report.export_stock_report.report_cek_cl'
    _description = 'Laporan Stok Penerimaan per Produk' 

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env['report.cek.cl.wizard'].browse(docids)
        kategori = wizard.kategori_selection.upper()

        selected_warehouses = wizard.warehouse_ids

        # === Filter produk per kategori ===
        products = self.env['product.product'].search([
            ('categ_id.name', '=', kategori)
        ])

        move_lines = self.env['stock.move.line'].search([
            ('picking_id.picking_type_id.code', '=', 'incoming'),
            ('product_id', 'in', products.ids),
        ])

        report_data = []

        # ================================================================
        # ===============   KATEGORI LOKAL (kode lama)  ==================
        # ================================================================
        if kategori == "LOKAL":
            # ---- kode lama yang sudah dibuat, biarkan ----
            # (Tidak dihapus agar tetap berjalan untuk kategori lokal)
            for product in products:
                product_moves = move_lines.filtered(lambda l: l.product_id == product)
                used_uoms = product_moves.mapped('product_uom_id').sorted(key=lambda u: u.name)

                warehouse_data = defaultdict(lambda: defaultdict(float))
                total_by_uom = defaultdict(lambda: {'box': 0, 'kg': 0})
                total_kg = 0

                for line in product_moves:
                    warehouse = self.env['stock.warehouse'].search([
                        ('lot_stock_id', 'parent_of', line.location_dest_id.id)
                    ], limit=1)
                    if not warehouse:
                        continue
                    if selected_warehouses and warehouse not in selected_warehouses:
                        continue

                    uom = line.product_uom_id
                    qty = line.quantity

                    warehouse_data[warehouse][uom] += qty

                warehouse_lines = []
                for wh, uom_qtys in warehouse_data.items():
                    wh_total_kg = 0
                    uom_struct = {}

                    for uom, qty in uom_qtys.items():
                        kg_value = qty * uom.factor_inv

                        uom_struct[uom] = {'box': qty, 'kg': kg_value}
                        total_by_uom[uom]['box'] += qty
                        total_by_uom[uom]['kg'] += kg_value
                        wh_total_kg += kg_value

                    warehouse_lines.append({
                        'warehouse': wh.name,
                        'uoms': uom_struct,
                        'total': wh_total_kg,
                    })

                    total_kg += wh_total_kg

                if total_kg == 0:
                    continue

                variant = product.product_template_variant_value_ids.mapped('name')
                variant_suffix = (" " + " ".join(variant)) if variant else ""
                product_display_name = product.name + variant_suffix

                report_data.append({
                    'product': product_display_name,
                    'uoms': used_uoms,
                    'warehouse_lines': warehouse_lines,
                    'total_by_uom': total_by_uom,
                    'total_kg': total_kg,
                })

        # ================================================================
        # ===============   KATEGORI EXPORT (BARU)       =================
        # ================================================================
        elif kategori == "EXPORT":

            quants = self.env['stock.quant'].search([
                ('product_id', 'in', products.ids),
                ('location_id.usage', '=', 'internal'),
            ])

            merged_map = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))

            # ============================================================
            # AMBIL BOX, GRADE, DAN CONT
            # ============================================================
            for product in products:

                tmpl = product.product_tmpl_id
                tmpl_attr_lines = tmpl.attribute_line_ids

                # --- BOX ---
                box_line = tmpl_attr_lines.filtered(
                    lambda l: l.attribute_id.name.strip().lower() == "box"
                )
                box_values = box_line.value_ids.mapped("name") if box_line else []
                box_name = box_values[0] if box_values else False
                if not box_name:
                    continue

                # --- GRADE ---
                variant_vals = product.product_template_variant_value_ids
                grade_values = variant_vals.filtered(
                    lambda v: v.attribute_id.name.strip().lower() == "grade"
                ).mapped("name")
                grade_name = grade_values[0] if grade_values else False
                if not grade_name:
                    continue

                # --- CONT ---
                cont_vals = variant_vals.filtered(
                    lambda v: v.attribute_id.name.strip().lower() == "cont"
                ).mapped("name")

                try:
                    cont_value = float(cont_vals[0]) if cont_vals else 1
                except:
                    cont_value = 1

                # ========================================================
                # ISI QTY
                # ========================================================
                product_quants = quants.filtered(lambda q: q.product_id == product)

                for q in product_quants:

                    warehouse = self.env['stock.warehouse'].search([
                        ('lot_stock_id', 'parent_of', q.location_id.id)
                    ], limit=1)

                    if not warehouse:
                        continue
                    if selected_warehouses and warehouse not in selected_warehouses:
                        continue

                    # qty dibagi cont + bulatkan
                    converted_qty = int(q.quantity / cont_value)

                    if converted_qty <= 0:
                        continue

                    merged_map[warehouse.name][box_name][grade_name] += converted_qty

            # ====================================================================================
            # STOP JIKA SEMUA QTY 0
            # ====================================================================================
            if not merged_map:
                return {
                    'doc_ids': docids,
                    'doc_model': 'report.cek.cl.wizard',
                    'docs': wizard,
                    'kategori': kategori,
                    'report_data': [],
                }

            # ====================================================================================
            # HITUNG TOTAL PER BOX × GRADE
            # ====================================================================================
            raw_box_grade_totals = defaultdict(lambda: defaultdict(int))

            for wh in merged_map.values():
                for box, grade_dict in wh.items():
                    for grade, qty in grade_dict.items():
                        raw_box_grade_totals[box][grade] += int(qty)

            # ====================================================================================
            # FILTER GRADE YANG TOTAL > 0
            # ====================================================================================
            grades_in_footer = sorted({
                grade
                for box in raw_box_grade_totals.values()
                for grade, qty in box.items()
                if qty > 0
            })

            if not grades_in_footer:
                return {
                    'doc_ids': docids,
                    'doc_model': 'report.cek.cl.wizard',
                    'docs': wizard,
                    'kategori': kategori,
                    'report_data': [],
                }

            # ====================================================================================
            # FILTER BOX YANG PUNYA GRADE > 0
            # ====================================================================================
            boxes_list = sorted([
                box for box, grades in raw_box_grade_totals.items()
                if any(grades.get(g, 0) > 0 for g in grades_in_footer)
            ])

            # ====================================================================================
            # BOX-GRADE TOTAL FINAL (HANYA YG > 0)
            # ====================================================================================
            box_grade_totals = {
                box: {
                    g: raw_box_grade_totals[box][g]
                    for g in grades_in_footer
                    if raw_box_grade_totals[box][g] > 0
                }
                for box in boxes_list
            }

            # ====================================================================================
            # WAREHOUSE LINES FINAL (KOSONG HILANG)
            # ====================================================================================
            warehouse_lines = []
            for wh_name, box_dict in merged_map.items():

                cleaned_boxes = {}
                total_wh = 0

                for box in boxes_list:
                    gdict = box_dict.get(box, {})
                    cleaned_gdict = {}

                    for g in grades_in_footer:
                        qty = int(gdict.get(g, 0))
                        if qty > 0:
                            cleaned_gdict[g] = qty
                            total_wh += qty

                    # hanya masukkan BOX yang punya grade
                    if cleaned_gdict:
                        cleaned_boxes[box] = cleaned_gdict

                if total_wh > 0:
                    warehouse_lines.append({
                        "warehouse": wh_name,
                        "boxes": cleaned_boxes,
                        "total": total_wh
                    })

            # ====================================================================================
            # GRAND TOTAL
            # ====================================================================================
            grand_total = sum(
                qty for box in box_grade_totals.values()
                for qty in box.values()
            )

            colspan_val = len(boxes_list) * len(grades_in_footer)

            report_data = [{
                "boxes": boxes_list,
                "grades": grades_in_footer,
                "warehouse_lines": warehouse_lines,
                "box_grade_totals": box_grade_totals,
                "colspan": colspan_val,
                "grand_total": grand_total,
            }]

        return {
            'doc_ids': docids,
            'doc_model': 'report.cek.cl.wizard',
            'docs': wizard,
            'kategori': kategori,
            'report_data': report_data,
        }

