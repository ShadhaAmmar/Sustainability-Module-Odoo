# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    carbon_emission = fields.Float("Émissions de la facture (kg CO2e)", compute='_compute_carbon_emission',
                                   digits=(16, 3))

    @api.depends('invoice_line_ids.product_id', 'invoice_line_ids.quantity',
                 'invoice_line_ids.product_uom_id', 'move_type')
    def _compute_carbon_emission(self):
        for move in self:
            total = 0.0
            for line in move.invoice_line_ids.filtered('product_id'):
                qty = line.product_uom_id._compute_quantity(line.quantity, line.product_id.uom_id) \
                    if line.product_uom_id else line.quantity
                total += qty * line.product_id.carbon_intensity
            move.carbon_emission = -total if move.move_type in ('out_refund', 'in_refund') else total
