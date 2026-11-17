# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MrpBom(models.Model):
    _inherit = 'mrp.bom'

    production_energy_kwh = fields.Float("Énergie de production (kWh par quantité de la nomenclature)")
    carbon_intensity_computed = fields.Float("Intensité carbone calculée (kg CO2e / unité)",
                                             compute='_compute_carbon_intensity_computed', digits=(16, 3))

    @api.depends('bom_line_ids.product_id.carbon_intensity', 'bom_line_ids.product_qty',
                 'bom_line_ids.product_uom_id', 'production_energy_kwh', 'product_qty', 'company_id')
    def _compute_carbon_intensity_computed(self):
        for bom in self:
            factor = self.env['carbon.factor']._get_default(bom.company_id or self.env.company)
            materials = 0.0
            for line in bom.bom_line_ids:
                qty = line.product_uom_id._compute_quantity(line.product_qty, line.product_id.uom_id)
                materials += qty * line.product_id.carbon_intensity
            energy = bom.production_energy_kwh * factor.electricity_factor if factor else 0.0
            bom.carbon_intensity_computed = (materials + energy) / (bom.product_qty or 1.0)

    def action_apply_carbon_intensity(self):
        self.ensure_one()
        if not self.product_tmpl_id:
            raise UserError(_("Cette nomenclature n'est liée à aucun produit."))
        self.product_tmpl_id.write({
            'carbon_intensity': self.carbon_intensity_computed,
            'carbon_intensity_source': 'bom',
            'carbon_intensity_note': self.display_name,
        })


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    carbon_footprint_ids = fields.One2many('carbon.footprint', 'production_id', copy=False)
    carbon_footprint_count = fields.Integer(compute='_compute_carbon_footprint_count')

    @api.depends('carbon_footprint_ids')
    def _compute_carbon_footprint_count(self):
        for production in self:
            production.carbon_footprint_count = len(production.sudo().carbon_footprint_ids)

    def button_mark_done(self):
        res = super().button_mark_done()
        footprint = self.env['carbon.footprint']
        for production in self.filtered(lambda m: m.state == 'done' and not m.sudo().carbon_footprint_ids):
            try:
                with self.env.cr.savepoint():
                    footprint._create_from_production(production)
            except Exception:
                _logger.exception("Création de l'empreinte carbone impossible pour %s", production.name)
        return res

    def action_carbon_footprint(self):
        self.ensure_one()
        footprints = self.sudo().carbon_footprint_ids
        if not footprints:
            footprints = self.env['carbon.footprint']._create_from_production(self)
        if not footprints:
            raise UserError(_("Aucun composant à évaluer sur cet ordre de fabrication."))
        return footprints._get_action()
