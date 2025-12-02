from odoo import models, fields, api, _
from odoo.exceptions import UserError

class StockPicking(models.Model):
    _inherit = "stock.picking"

    sales_person_id = fields.Many2one(
        'res.users',
        string='Sales Person'
    )

    person_ids = fields.Many2one(
        'res.users',
        string='Sales Person'
    )

    @api.model_create_multi
    def create(self, vals_list):
        pickings = super().create(vals_list)
        pickings._check_sales_person_responsible()
        return pickings

    def write(self, vals):
        res = super().write(vals)
        self._check_sales_person_responsible()
        return res

    def _check_sales_person_responsible(self):
        """Cek apakah sales_person_id sesuai dengan sales_person_ids di setiap product"""
        for picking in self:
            if not picking.sales_person_id:
                continue

            for move in picking.move_ids_without_package:
                product = move.product_id
                if product.sales_person_ids and picking.sales_person_id not in product.sales_person_ids:
                    raise UserError(_(
                        "Sales Person '%s' tidak sesuai untuk produk '%s'. "
                        "Produk ini hanya boleh diproses oleh: %s"
                    ) % (
                        picking.sales_person_id.name,
                        product.display_name,
                        ", ".join(product.sales_person_ids.mapped("name"))
                    ))
