# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    carbon_footprint_ids = fields.One2many('carbon.footprint', 'purchase_order_id', copy=False)
    carbon_footprint_count = fields.Integer(compute='_compute_carbon_footprint_count')
    estimated_carbon_emission = fields.Float("Émissions estimées (kg CO2e)",
                                             compute='_compute_estimated_carbon_emission', digits=(16, 3))
    supplier_esg_score = fields.Float(related='partner_id.esg_score', string="Score ESG fournisseur")
    supplier_esg_rating = fields.Selection(related='partner_id.esg_rating', string="Note ESG fournisseur")

    @api.depends('carbon_footprint_ids')
    def _compute_carbon_footprint_count(self):
        for order in self:
            order.carbon_footprint_count = len(order.sudo().carbon_footprint_ids)

    @api.depends('order_line.line_carbon_emission')
    def _compute_estimated_carbon_emission(self):
        for order in self:
            order.estimated_carbon_emission = sum(order.order_line.mapped('line_carbon_emission'))

    @api.onchange('partner_id')
    def _onchange_partner_esg_warning(self):
        partner = self.partner_id
        if partner and partner.esg_scoring_count:
            threshold = float(self.env['ir.config_parameter'].sudo().get_param(
                'carbon_footprint_management.esg_min_score', 50))
            if partner.esg_score < threshold:
                return {'warning': {
                    'title': _("Fournisseur à risque ESG"),
                    'message': _("%(partner)s a un score ESG de %(score).1f/100, sous le seuil de %(threshold).0f.",
                                 partner=partner.display_name, score=partner.esg_score, threshold=threshold),
                }}

    def button_confirm(self):
        res = super().button_confirm()
        footprint = self.env['carbon.footprint']
        for order in self.filtered(lambda o: o.state in ('purchase', 'done') and not o.sudo().carbon_footprint_ids):
            try:
                with self.env.cr.savepoint():
                    footprint._create_from_purchase(order)
            except Exception:
                _logger.exception("Création de l'empreinte carbone impossible pour %s", order.name)
        return res

    def action_carbon_footprint(self):
        self.ensure_one()
        footprints = self.sudo().carbon_footprint_ids
        if not footprints:
            footprints = self.env['carbon.footprint']._create_from_purchase(self)
        if not footprints:
            raise UserError(_("Aucune ligne produit à évaluer sur cette commande."))
        return footprints._get_action()


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    carbon_intensity = fields.Float(related='product_id.carbon_intensity', string="Intensité carbone")
    line_carbon_emission = fields.Float("CO2e (kg)", compute='_compute_line_carbon_emission', digits=(16, 3))

    @api.depends('product_id', 'product_qty', 'product_uom')
    def _compute_line_carbon_emission(self):
        for line in self:
            if line.product_id:
                qty = line.product_uom._compute_quantity(line.product_qty, line.product_id.uom_id) \
                    if line.product_uom else line.product_qty
                line.line_carbon_emission = qty * line.product_id.carbon_intensity
            else:
                line.line_carbon_emission = 0.0

    def action_carbon_alternatives(self):
        self.ensure_one()
        return self.env['carbon.alternative.wizard']._open(self.product_id, self)
