from odoo import models, api
from collections import defaultdict

class ReportCekCL(models.AbstractModel):
    _name = 'report.export_stock_report.report_cek_cl'
    _description = 'Laporan Stok Penerimaan per Produk'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env['report.cek.cl.wizard'].browse(docids)
        kategori = wizard.kategori_selection.upper()

        # === Filter warehouse yang dipilih (jika diisi) ===
        selected_warehouses = wizard.warehouse_ids

        # === Filter produk berdasarkan kategori ===
        products = self.env['product.product'].search([
            ('categ_id.name', '=', kategori)
        ])

        # === Ambil stock move lines incoming ===
        move_lines = self.env['stock.move.line'].search([
            ('picking_id.picking_type_id.code', '=', 'incoming'),
            ('product_id', 'in', products.ids),
        ])

        report_data = []

        for product in products:
            product_moves = move_lines.filtered(lambda l: l.product_id == product)
            used_uoms = product_moves.mapped('product_uom_id').sorted(key=lambda u: u.name)

            warehouse_data = defaultdict(lambda: defaultdict(float))
            total_by_uom = defaultdict(lambda: {'box': 0, 'kg': 0})
            total_kg = 0

            for line in product_moves:
                # Cari warehouse berdasarkan lokasi dest
                warehouse = self.env['stock.warehouse'].search([
                    ('lot_stock_id', 'parent_of', line.location_dest_id.id)
                ], limit=1)
                if not warehouse:
                    continue

                # === Skip warehouse yg tidak dipilih ===
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

                    uom_struct[uom] = {
                        'box': qty,
                        'kg': kg_value,
                    }

                    total_by_uom[uom]['box'] += qty
                    total_by_uom[uom]['kg'] += kg_value
                    wh_total_kg += kg_value

                warehouse_lines.append({
                    'warehouse': wh.name,
                    'uoms': uom_struct,
                    'total': wh_total_kg,
                })

                total_kg += wh_total_kg

            # Skip jika tidak ada data
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

        return {
            'doc_ids': docids,
            'doc_model': 'report.cek.cl.wizard',
            'docs': wizard,
            'kategori': kategori,
            'report_data': report_data,
        }
