# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    carbon_intensity = fields.Float("Intensité carbone (kg CO2e / unité)", digits=(16, 3), tracking=True)
    carbon_intensity_source = fields.Selection([
        ('manual', "Saisie manuelle"),
        ('supplier', "Donnée fournisseur (EPD / FDES)"),
        ('database', "Base de facteurs (ADEME, ecoinvent...)"),
        ('bom', "Calculée depuis la nomenclature"),
    ], string="Source de la donnée")
    carbon_intensity_note = fields.Char("Référence de la donnée")
    carbon_in_stock = fields.Float("Carbone en stock (kg CO2e)", compute='_compute_carbon_in_stock',
                                   digits=(16, 3))
    recyclable = fields.Boolean("Recyclable")
    recycled_content = fields.Float("Part de matière recyclée (%)")
    eco_alternative_ids = fields.Many2many(
        'product.template', 'product_eco_alternative_rel', 'product_id', 'alternative_id',
        string="Alternatives écologiques")

    @api.depends('qty_available', 'carbon_intensity')
    def _compute_carbon_in_stock(self):
        for tmpl in self:
            tmpl.carbon_in_stock = tmpl.qty_available * tmpl.carbon_intensity

    @api.constrains('recycled_content')
    def _check_recycled_content(self):
        for tmpl in self:
            if not 0 <= tmpl.recycled_content <= 100:
                raise ValidationError(_("La part de matière recyclée doit être comprise entre 0 et 100 %."))

    def action_carbon_alternatives(self):
        self.ensure_one()
        return self.env['carbon.alternative.wizard']._open(self.product_variant_id)
