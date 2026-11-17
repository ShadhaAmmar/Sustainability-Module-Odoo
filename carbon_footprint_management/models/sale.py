# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    carbon_footprint_ids = fields.One2many('carbon.footprint', 'sale_order_id', copy=False)
    carbon_footprint_count = fields.Integer(compute='_compute_carbon_footprint_count')

    @api.depends('carbon_footprint_ids')
    def _compute_carbon_footprint_count(self):
        for order in self:
            order.carbon_footprint_count = len(order.sudo().carbon_footprint_ids)

    def action_confirm(self):
        res = super().action_confirm()
        footprint = self.env['carbon.footprint']
        for order in self.filtered(lambda o: o.state == 'sale' and not o.sudo().carbon_footprint_ids):
            try:
                with self.env.cr.savepoint():
                    footprint._create_from_sale(order)
            except Exception:
                _logger.exception("Création de l'empreinte carbone impossible pour %s", order.name)
        return res

    def action_carbon_footprint(self):
        self.ensure_one()
        footprints = self.sudo().carbon_footprint_ids
        if not footprints:
            footprints = self.env['carbon.footprint']._create_from_sale(self)
        if not footprints:
            raise UserError(_("Aucune ligne produit à évaluer sur cette commande."))
        return footprints._get_action()
