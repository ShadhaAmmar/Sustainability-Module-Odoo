# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class CarbonCertificate(models.Model):
    _name = 'carbon.certificate'
    _description = "Certificat carbone"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char("Numéro", required=True, copy=False, readonly=True, default=lambda self: _('New'))
    footprint_id = fields.Many2one('carbon.footprint', string="Empreinte carbone", required=True,
                                   ondelete='restrict', tracking=True)
    company_id = fields.Many2one('res.company', related='footprint_id.company_id', store=True)
    partner_id = fields.Many2one('res.partner', string="Client", required=True, tracking=True)
    date = fields.Date("Date d'émission", default=fields.Date.context_today, required=True)
    validity_date = fields.Date("Valable jusqu'au",
                                default=lambda self: fields.Date.context_today(self) + relativedelta(years=1))
    emission = fields.Float("Émissions (kg CO2e)", digits=(16, 3), readonly=True)
    offset_kg = fields.Float("Compensation (kg CO2e)", digits=(16, 3), tracking=True)
    net_emission = fields.Float("Émissions nettes (kg CO2e)", digits=(16, 3),
                                compute='_compute_net', store=True)
    certificate_type = fields.Selection([
        ('footprint', "Empreinte carbone"),
        ('neutral', "Neutralité carbone (compensation)"),
    ], string="Type", compute='_compute_net', store=True)
    methodology = fields.Text("Méthodologie")
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('issued', 'Émis'),
        ('cancelled', 'Annulé'),
    ], default='draft', required=True, tracking=True, copy=False)
    verified_by = fields.Many2one('res.users', string="Vérifié par", readonly=True, copy=False)
    verification_date = fields.Date("Date de vérification", readonly=True, copy=False)

    @api.depends('emission', 'offset_kg')
    def _compute_net(self):
        for rec in self:
            rec.net_emission = max(rec.emission - rec.offset_kg, 0.0)
            rec.certificate_type = 'neutral' if rec.emission > 0 and rec.offset_kg >= rec.emission else 'footprint'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('carbon.certificate') or _('New')
            footprint = self.env['carbon.footprint'].browse(vals.get('footprint_id'))
            if footprint:
                vals.setdefault('emission', footprint.total_emission)
                vals.setdefault('methodology', _(
                    "Calcul selon le GHG Protocol (scopes 1, 2 et 3) avec le jeu de facteurs d'émission « %s ».",
                    footprint.factor_id.name or '-'))
        return super().create(vals_list)

    def action_issue(self):
        for rec in self:
            rec.state = 'issued'
            rec.message_post(body=_("Certificat émis."))

    def action_cancel(self):
        for rec in self:
            rec.state = 'cancelled'
            if rec.footprint_id.state == 'certified' and not (rec.footprint_id.certificate_ids - rec).filtered(
                    lambda c: c.state != 'cancelled'):
                rec.footprint_id.state = 'validated'

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_verify(self):
        if not self.env.user.has_group('carbon_footprint_management.group_carbon_manager'):
            raise AccessError(_("Seul un responsable durabilité peut marquer un certificat comme vérifié."))
        self.write({'verified_by': self.env.user.id, 'verification_date': fields.Date.context_today(self)})

    def action_print(self):
        self.ensure_one()
        if self.state == 'draft':
            raise UserError(_("Émettez le certificat avant de l'imprimer."))
        return self.env.ref('carbon_footprint_management.action_report_carbon_certificate').report_action(self)
