from odoo import models, api
from collections import defaultdict
import time
import re
import random


class ReportDalamPengiriman(models.AbstractModel):
    _name = 'report.export_stock_report.stock_report_pengiriman'
    _description = 'Stock Report Dalam Pengiriman (Internal Transfer - Ready)'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env['pengiriman.report.wizard'].browse(docids)

        # ===== Domain picking: hanya internal & ready =====
        domain = [
            ('picking_type_code', '=', 'internal'),
            ('state', '=', 'assigned'),  # hanya status "Ready"
            ('scheduled_date', '<=', wizard.end_date),
        ]

        # ===== Tambahkan filter warehouse jika dipilih =====
        if wizard.warehouse_ids:
            domain.append(('picking_type_id.warehouse_id', 'in', wizard.warehouse_ids.ids))

        # ===== Ambil data picking =====
        pickings = self.env['stock.picking'].search(domain)

        # ===== Grouping data: per warehouse -> product variant -> grade =====
        result = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

        for picking in pickings:
            warehouse = picking.picking_type_id.warehouse_id.name or 'Tanpa Warehouse'
            for move in picking.move_ids_without_package:
                product = move.product_id
                design = product.product_tmpl_id.name
                # grade = ', '.join(product.product_template_attribute_value_ids.mapped('name')) or '-'
                grade_value = product.product_template_attribute_value_ids.filtered(
                    lambda v: 'grade' in v.attribute_id.name.lower()
                )

                grade = grade_value[0].name if grade_value else '-'
                qty = move.product_uom_qty
                destination = picking.location_dest_id.display_name
                origin = picking.origin or '-'
                # etd = picking.scheduled_date
                # eta = picking.date_deadline

                result[warehouse][design][grade].append({
                    'origin': origin,
                    # 'etd': etd,
                    # 'eta': eta,
                    'product': design,
                    'grade': grade,
                    'qty': qty,
                    'destination': destination,
                    'ket': picking.note or '-',
                })

        # ===== Buat total per design (summary per warehouse) =====
        total_per_design = {}
        for warehouse, design_dict in result.items():
            total_per_design[warehouse] = []
            for design, grade_dict in design_dict.items():
                total_box = sum(sum(line['qty'] for line in lines) for lines in grade_dict.values())
                cont_attr = None
                sample_line = next(iter(next(iter(grade_dict.values()))), None)

                if sample_line:
                    sample_product = self.env['product.product'].search([
                        ('name', '=', sample_line['product'])
                    ], limit=1)

                    # Cari attribute bernama "CONT"
                    cont_attr_val = sample_product.product_template_attribute_value_ids.filtered(
                        lambda v: 'cont' in v.attribute_id.name.lower()
                    )

                    if cont_attr_val:
                        # Asumsi value numeric misalnya "3100"
                        try:
                            cont_attr = float(cont_attr_val[0].name)
                        except:
                            cont_attr = None

                # ===== Hitung total container =====
                if cont_attr and cont_attr > 0:
                    total_cont = total_box / cont_attr
                else:
                    total_cont = total_box / 3100.0
                total_per_design[warehouse].append({
                    'design': design,
                    'total_box': total_box,
                    'total_cont': total_cont,
                })

        return {
            'doc_ids': docids,
            'doc_model': 'pengiriman.report.wizard',
            'docs': wizard,
            'wizard': wizard,
            'result': result,
            'total_per_design': total_per_design,
            'time': time,
        }

