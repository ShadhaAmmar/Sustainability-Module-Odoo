# -*- coding: utf-8 -*-
import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .carbon_factor import TRANSPORT_MODES

_logger = logging.getLogger(__name__)

EMISSION_DIGITS = (16, 3)
LOCKED_FIELDS = {
    'date', 'source', 'partner_id', 'factor_id', 'line_ids', 'transport_mode',
    'transport_distance', 'electricity_kwh', 'gas_kwh', 'packaging_weight',
}
COMPUTE_DEPENDS = (
    'line_ids.emission', 'line_ids.weight_kg', 'transport_mode', 'transport_distance',
    'electricity_kwh', 'gas_kwh', 'packaging_weight',
    'factor_id.electricity_factor', 'factor_id.gas_factor', 'factor_id.packaging_factor',
    'factor_id.transport_road_factor', 'factor_id.transport_rail_factor',
    'factor_id.transport_sea_factor', 'factor_id.transport_air_factor',
    'factor_id.transport_multi_factor', 'factor_id.carbon_price',
)


class CarbonFootprint(models.Model):
    _name = 'carbon.footprint'
    _description = "Empreinte carbone"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char("Référence", required=True, copy=False, readonly=True,
                       default=lambda self: _('New'))
    date = fields.Date("Date", required=True, default=fields.Date.context_today, tracking=True)
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('validated', 'Validée'),
        ('certified', 'Certifiée'),
    ], string="Statut", default='draft', required=True, tracking=True, copy=False)
    source = fields.Selection([
        ('manual', 'Saisie manuelle'),
        ('purchase', "Commande d'achat"),
        ('sale', 'Commande de vente'),
        ('production', 'Ordre de fabrication'),
    ], string="Origine", default='manual', required=True)
    partner_id = fields.Many2one('res.partner', string="Partenaire", tracking=True)
    purchase_order_id = fields.Many2one('purchase.order', string="Commande d'achat",
                                        readonly=True, copy=False, index=True)
    sale_order_id = fields.Many2one('sale.order', string="Commande de vente",
                                    readonly=True, copy=False, index=True)
    production_id = fields.Many2one('mrp.production', string="Ordre de fabrication",
                                    readonly=True, copy=False, index=True)
    company_id = fields.Many2one('res.company', string="Société", required=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    factor_id = fields.Many2one('carbon.factor', string="Facteurs d'émission",
                                default=lambda self: self.env['carbon.factor']._get_default())

    line_ids = fields.One2many('carbon.footprint.line', 'footprint_id', string="Produits", copy=True)
    transport_mode = fields.Selection(TRANSPORT_MODES, string="Mode de transport")
    transport_distance = fields.Float("Distance de transport (km)")
    electricity_kwh = fields.Float("Électricité consommée (kWh)")
    gas_kwh = fields.Float("Gaz consommé (kWh)")
    packaging_weight = fields.Float("Poids d'emballage (kg)")

    material_emission = fields.Float("Matières / produits (kg CO2e)", compute='_compute_emissions',
                                     store=True, digits=EMISSION_DIGITS)
    transport_emission = fields.Float("Transport (kg CO2e)", compute='_compute_emissions',
                                      store=True, digits=EMISSION_DIGITS)
    packaging_emission = fields.Float("Emballage (kg CO2e)", compute='_compute_emissions',
                                      store=True, digits=EMISSION_DIGITS)
    scope1_emission = fields.Float("Scope 1 (kg CO2e)", compute='_compute_emissions',
                                   store=True, digits=EMISSION_DIGITS)
    scope2_emission = fields.Float("Scope 2 (kg CO2e)", compute='_compute_emissions',
                                   store=True, digits=EMISSION_DIGITS)
    scope3_emission = fields.Float("Scope 3 (kg CO2e)", compute='_compute_emissions',
                                   store=True, digits=EMISSION_DIGITS)
    total_emission = fields.Float("Total (kg CO2e)", compute='_compute_emissions',
                                  store=True, digits=EMISSION_DIGITS, tracking=True)
    carbon_cost = fields.Monetary("Coût carbone estimé", compute='_compute_emissions',
                                  store=True, currency_field='currency_id')

    certificate_ids = fields.One2many('carbon.certificate', 'footprint_id', string="Certificats")
    certificate_count = fields.Integer(compute='_compute_certificate_count')
    notes = fields.Text("Notes")

    @api.depends(*COMPUTE_DEPENDS)
    def _compute_emissions(self):
        for rec in self:
            factor = rec.factor_id
            material = sum(rec.line_ids.mapped('emission'))
            weight_t = sum(rec.line_ids.mapped('weight_kg')) / 1000.0
            transport = 0.0
            if factor and rec.transport_mode and rec.transport_distance:
                transport = weight_t * rec.transport_distance * factor.get_transport_factor(rec.transport_mode)
            packaging = rec.packaging_weight * factor.packaging_factor if factor else 0.0
            scope1 = rec.gas_kwh * factor.gas_factor if factor else 0.0
            scope2 = rec.electricity_kwh * factor.electricity_factor if factor else 0.0
            scope3 = material + transport + packaging
            total = scope1 + scope2 + scope3
            rec.material_emission = material
            rec.transport_emission = transport
            rec.packaging_emission = packaging
            rec.scope1_emission = scope1
            rec.scope2_emission = scope2
            rec.scope3_emission = scope3
            rec.total_emission = total
            rec.carbon_cost = total / 1000.0 * factor.carbon_price if factor else 0.0

    @api.depends('certificate_ids')
    def _compute_certificate_count(self):
        for rec in self:
            rec.certificate_count = len(rec.certificate_ids)

    # ------------------------------------------------------------------ ORM
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('carbon.footprint') or _('New')
        return super().create(vals_list)

    def write(self, vals):
        if LOCKED_FIELDS & set(vals) and any(rec.state != 'draft' for rec in self):
            raise UserError(_("Une empreinte validée ne peut plus être modifiée. "
                              "Remettez-la d'abord en brouillon."))
        return super().write(vals)

    def unlink(self):
        if any(rec.state != 'draft' for rec in self):
            raise UserError(_("Seules les empreintes en brouillon peuvent être supprimées."))
        return super().unlink()

    # -------------------------------------------------------------- Workflow
    def action_validate(self):
        if not (self.env.su or self.env.user.has_group('carbon_footprint_management.group_carbon_manager')):
            raise AccessError(_("Seul un responsable durabilité peut valider une empreinte."))
        for rec in self:
            if rec.state != 'draft':
                continue
            if not rec.line_ids and not (rec.electricity_kwh or rec.gas_kwh or rec.packaging_weight):
                raise UserError(_("Aucune donnée à valider pour %s.", rec.name))
            rec.state = 'validated'

    def action_draft(self):
        for rec in self:
            if rec.state == 'certified':
                raise UserError(_("Une empreinte certifiée ne peut pas repasser en brouillon : "
                                  "annulez d'abord son certificat."))
            rec.state = 'draft'

    def action_certify(self):
        self.ensure_one()
        if self.state == 'draft':
            raise UserError(_("Validez l'empreinte avant de générer un certificat."))
        cert = self.certificate_ids.filtered(lambda c: c.state != 'cancelled')[:1]
        if not cert:
            if not self.partner_id:
                raise UserError(_("Renseignez le partenaire (client) pour émettre un certificat."))
            cert = self.env['carbon.certificate'].create({
                'footprint_id': self.id,
                'partner_id': self.partner_id.id,
            })
            self.state = 'certified'
        return {
            'type': 'ir.actions.act_window',
            'name': _("Certificat carbone"),
            'res_model': 'carbon.certificate',
            'res_id': cert.id,
            'view_mode': 'form',
        }

    def action_view_certificates(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Certificats carbone"),
            'res_model': 'carbon.certificate',
            'view_mode': 'tree,form',
            'domain': [('footprint_id', '=', self.id)],
        }

    def _get_action(self):
        action = {
            'type': 'ir.actions.act_window',
            'name': _("Empreinte carbone"),
            'res_model': 'carbon.footprint',
        }
        if len(self) == 1:
            action.update(view_mode='form', res_id=self.id)
        else:
            action.update(view_mode='tree,form', domain=[('id', 'in', self.ids)])
        return action

    # ------------------------------------------------- Création automatique
    @api.model
    def _line_vals(self, product, qty, uom):
        qty_product_uom = uom._compute_quantity(qty, product.uom_id) if uom else qty
        return {'product_id': product.id, 'quantity': qty_product_uom}

    @api.model
    def _create_from_lines(self, source, company, date, lines, extra=None):
        if not lines:
            return self.browse()
        vals = {
            'source': source,
            'company_id': company.id,
            'date': date,
            'line_ids': [(0, 0, line) for line in lines],
        }
        vals.update(extra or {})
        return self.with_company(company).sudo().create(vals)

    @api.model
    def _create_from_purchase(self, order):
        lines = [self._line_vals(l.product_id, l.product_qty, l.product_uom)
                 for l in order.order_line if l.product_id and not l.display_type]
        date = order.date_order.date() if order.date_order else fields.Date.context_today(self)
        return self._create_from_lines('purchase', order.company_id, date, lines, {
            'purchase_order_id': order.id, 'partner_id': order.partner_id.id,
        })

    @api.model
    def _create_from_sale(self, order):
        lines = [self._line_vals(l.product_id, l.product_uom_qty, l.product_uom)
                 for l in order.order_line if l.product_id and not l.display_type]
        date = order.date_order.date() if order.date_order else fields.Date.context_today(self)
        return self._create_from_lines('sale', order.company_id, date, lines, {
            'sale_order_id': order.id, 'partner_id': order.partner_id.id,
        })

    @api.model
    def _create_from_production(self, production):
        lines = []
        for move in production.move_raw_ids.filtered(lambda m: m.state != 'cancel' and m.product_id):
            qty = move.quantity or move.product_uom_qty
            lines.append(self._line_vals(move.product_id, qty, move.product_uom))
        bom = production.bom_id
        energy = 0.0
        if bom:
            energy = bom.production_energy_kwh * production.product_qty / (bom.product_qty or 1.0)
        date = (production.date_finished or fields.Datetime.now()).date()
        return self._create_from_lines('production', production.company_id, date, lines, {
            'production_id': production.id, 'electricity_kwh': energy,
        })


class CarbonFootprintLine(models.Model):
    _name = 'carbon.footprint.line'
    _description = "Ligne d'empreinte carbone"

    footprint_id = fields.Many2one('carbon.footprint', required=True, ondelete='cascade', index=True)
    product_id = fields.Many2one('product.product', string="Produit", required=True)
    quantity = fields.Float("Quantité", default=1.0, digits='Product Unit of Measure')
    uom_id = fields.Many2one(related='product_id.uom_id', string="Unité")
    intensity = fields.Float("Intensité (kg CO2e / unité)", digits=(16, 3),
                             compute='_compute_intensity', store=True, readonly=False, precompute=True)
    weight_kg = fields.Float("Poids (kg)", compute='_compute_weight', store=True, digits=(16, 3))
    emission = fields.Float("Émission (kg CO2e)", compute='_compute_emission', store=True,
                            digits=EMISSION_DIGITS)

    @api.depends('product_id')
    def _compute_intensity(self):
        for line in self:
            line.intensity = line.product_id.carbon_intensity

    @api.depends('product_id.weight', 'quantity')
    def _compute_weight(self):
        for line in self:
            line.weight_kg = line.product_id.weight * line.quantity

    @api.depends('quantity', 'intensity')
    def _compute_emission(self):
        for line in self:
            line.emission = line.quantity * line.intensity

    def _check_parent_draft(self, footprints):
        if any(fp.state != 'draft' for fp in footprints):
            raise UserError(_("Les lignes d'une empreinte validée ne sont plus modifiables."))

    @api.model_create_multi
    def create(self, vals_list):
        footprints = self.env['carbon.footprint'].browse([v['footprint_id'] for v in vals_list if v.get('footprint_id')])
        self._check_parent_draft(footprints)
        return super().create(vals_list)

    def write(self, vals):
        self._check_parent_draft(self.footprint_id)
        return super().write(vals)

    def unlink(self):
        self._check_parent_draft(self.footprint_id)
        return super().unlink()
