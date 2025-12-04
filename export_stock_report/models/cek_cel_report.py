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
            merged_map = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
            used_uoms = set()
            used_grades = set()

            for product in products:

                # grade product
                grade_values = product.product_template_variant_value_ids.filtered(
                    lambda v: v.attribute_id.name and v.attribute_id.name.strip().lower() == "grade"
                ).mapped('name')

                if not grade_values:
                    continue

                product_moves = move_lines.filtered(lambda l: l.product_id == product)

                for line in product_moves:

                    warehouse = self.env['stock.warehouse'].search([
                        ('lot_stock_id', 'parent_of', line.location_dest_id.id)
                    ], limit=1)
                    if not warehouse:
                        continue
                    if selected_warehouses and warehouse not in selected_warehouses:
                        continue

                    uom = line.product_uom_id
                    uom_name = uom.name if uom else "UNKN"
                    qty = line.quantity
                    grade_name = grade_values[0]    # ambil grade produk

                    used_uoms.add(uom_name)
                    used_grades.add(grade_name)

                    merged_map[warehouse.name][uom_name][grade_name] += qty

            # jika kosong
            if not merged_map:
                return {...}

            # susun warehouse_lines final
            warehouse_lines = []
            for wh_name, uom_dict in merged_map.items():
                total_wh = 0
                uom_struct = {}
                for uom_name, grade_dict in uom_dict.items():
                    uom_struct[uom_name] = {}
                    for grade_name, qty in grade_dict.items():
                        uom_struct[uom_name][grade_name] = qty
                        total_wh += qty
                warehouse_lines.append({
                    "warehouse": wh_name,
                    "uoms": uom_struct,
                    "total": total_wh,
                })

            # uoms & grades final
            uoms_list = sorted(list(used_uoms))
            grades_list = sorted(list(used_grades))

            colspan_val = len(uoms_list) * len(grades_list)

            report_data = [{
                "uoms": uoms_list,
                "grades": grades_list,
                "warehouse_lines": warehouse_lines,
                "colspan": colspan_val,
            }]


        return {
            'doc_ids': docids,
            'doc_model': 'report.cek.cl.wizard',
            'docs': wizard,
            'kategori': kategori,
            'report_data': report_data,
        }
