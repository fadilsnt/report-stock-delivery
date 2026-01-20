from odoo import models, fields

class StockMove(models.Model):
    _inherit = 'stock.move'

    no_cont = fields.Char(
        string='No. Container',
        help='Nomor container untuk pengiriman'
    )

    keterangan = fields.Char(
        string='Keterangan',
        help='Keterangan tambahan pengiriman'
    )
