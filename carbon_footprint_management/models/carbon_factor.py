# -*- coding: utf-8 -*-
from odoo import api, fields, models

TRANSPORT_MODES = [
    ('road', 'Route'),
    ('rail', 'Rail'),
    ('sea', 'Maritime'),
    ('air', 'Aérien'),
    ('multi', 'Multimodal'),
]


class CarbonFactor(models.Model):
    _name = 'carbon.factor'
    _description = "Jeu de facteurs d'émission"
    _order = 'sequence, id'

    name = fields.Char("Nom", required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', string="Société", required=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    reference = fields.Char("Source des facteurs")

    electricity_factor = fields.Float("Électricité (kg CO2e / kWh)", digits=(16, 4), default=0.25)
    gas_factor = fields.Float("Gaz naturel (kg CO2e / kWh)", digits=(16, 4), default=0.184)
    transport_road_factor = fields.Float("Route (kg CO2e / t.km)", digits=(16, 4), default=0.10)
    transport_rail_factor = fields.Float("Rail (kg CO2e / t.km)", digits=(16, 4), default=0.025)
    transport_sea_factor = fields.Float("Maritime (kg CO2e / t.km)", digits=(16, 4), default=0.015)
    transport_air_factor = fields.Float("Aérien (kg CO2e / t.km)", digits=(16, 4), default=0.60)
    transport_multi_factor = fields.Float("Multimodal (kg CO2e / t.km)", digits=(16, 4), default=0.06)
    packaging_factor = fields.Float("Emballage (kg CO2e / kg)", digits=(16, 4), default=1.5)
    carbon_price = fields.Monetary("Prix du carbone (par tCO2e)", currency_field='currency_id',
                                   default=80.0)

    def get_transport_factor(self, mode):
        self.ensure_one()
        return {
            'road': self.transport_road_factor,
            'rail': self.transport_rail_factor,
            'sea': self.transport_sea_factor,
            'air': self.transport_air_factor,
            'multi': self.transport_multi_factor,
        }.get(mode, 0.0)

    @api.model
    def _get_default(self, company=None):
        company = company or self.env.company
        return self.search([('company_id', '=', company.id)], order='sequence, id', limit=1)
