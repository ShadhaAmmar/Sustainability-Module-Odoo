# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

METHODOLOGY = (
    "<p>Inventaire établi selon le GHG Protocol : Scope 1 (combustibles), Scope 2 (électricité, "
    "méthode basée sur la localisation) et Scope 3 (achats de biens et services, transport amont, "
    "emballages).</p>"
    "<p><b>Périmètre et anti double comptage :</b> seules les empreintes <i>validées ou certifiées</i> "
    "sont retenues. Les empreintes de vente (empreinte produit communiquée aux clients) sont exclues "
    "de l'inventaire ; pour les ordres de fabrication, seuls les scopes 1 et 2 sont retenus car les "
    "matières consommées sont déjà comptées via les achats (Scope 3).</p>"
    "<p><b>Limites :</b> les facteurs d'émission sont ceux du jeu configuré dans l'application ; "
    "ce rapport structure les données attendues par l'ESRS E1 mais ne constitue pas, à lui seul, une "
    "déclaration CSRD (balisage numérique, double matérialité, assurance de durabilité restent à votre charge).</p>"
)


class CarbonReport(models.Model):
    _name = 'carbon.report'
    _description = "Rapport de durabilité"
    _inherit = ['mail.thread']
    _order = 'date_from desc, id desc'

    name = fields.Char("Titre", required=True)
    company_id = fields.Many2one('res.company', string="Société", required=True,
                                 default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id')
    date_from = fields.Date("Du", required=True)
    date_to = fields.Date("Au", required=True)
    framework = fields.Selection([
        ('esrs_e1', "CSRD – ESRS E1 (changement climatique)"),
        ('ghg', "GHG Protocol – inventaire"),
        ('internal', "Suivi interne"),
    ], string="Référentiel", default='esrs_e1', required=True)
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('computed', 'Calculé'),
        ('published', 'Publié'),
    ], default='draft', required=True, tracking=True)

    scope1_t = fields.Float("Scope 1 (tCO2e)", digits=(16, 3), readonly=True)
    scope2_t = fields.Float("Scope 2 (tCO2e)", digits=(16, 3), readonly=True)
    scope3_t = fields.Float("Scope 3 (tCO2e)", digits=(16, 3), readonly=True)
    total_t = fields.Float("Total (tCO2e)", digits=(16, 3), readonly=True)
    electricity_kwh = fields.Float("Électricité (kWh)", readonly=True)
    gas_kwh = fields.Float("Gaz (kWh)", readonly=True)
    revenue = fields.Monetary("Chiffre d'affaires net (période)", currency_field='currency_id', readonly=True)
    intensity = fields.Float("Intensité GES (tCO2e / M de CA)", digits=(16, 3), readonly=True)
    previous_total_t = fields.Float("Total période précédente (tCO2e)", digits=(16, 3), readonly=True)
    change_pct = fields.Float("Variation (%)", digits=(16, 1), readonly=True)
    target_total_t = fields.Float("Objectif de la période (tCO2e)", digits=(16, 3))
    target_gap_t = fields.Float("Écart à l'objectif (tCO2e)", digits=(16, 3), readonly=True)
    footprint_count = fields.Integer("Empreintes retenues", readonly=True)
    supplier_count = fields.Integer("Fournisseurs actifs", readonly=True)
    supplier_evaluated_pct = fields.Float("Fournisseurs évalués ESG (%)", digits=(16, 1), readonly=True)
    supplier_avg_esg = fields.Float("Score ESG moyen des fournisseurs", digits=(16, 1), readonly=True)
    methodology = fields.Html("Méthodologie et limites", default=METHODOLOGY)
    notes = fields.Html("Commentaires de la direction")

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from > rec.date_to:
                raise ValidationError(_("La date de début doit précéder la date de fin."))

    def _period_totals(self, date_from, date_to):
        self.ensure_one()
        footprints = self.env['carbon.footprint'].search([
            ('company_id', '=', self.company_id.id),
            ('date', '>=', date_from), ('date', '<=', date_to),
            ('state', 'in', ('validated', 'certified')),
            ('source', '!=', 'sale'),
        ])
        res = dict(s1=0.0, s2=0.0, s3=0.0, elec=0.0, gas=0.0, count=len(footprints))
        for fp in footprints:
            res['s1'] += fp.scope1_emission
            res['s2'] += fp.scope2_emission
            if fp.source != 'production':
                res['s3'] += fp.scope3_emission
            res['elec'] += fp.electricity_kwh
            res['gas'] += fp.gas_kwh
        res['total'] = res['s1'] + res['s2'] + res['s3']
        return res

    def action_compute(self):
        for rec in self:
            cur = rec._period_totals(rec.date_from, rec.date_to)
            days = (rec.date_to - rec.date_from).days + 1
            prev_to = rec.date_from - timedelta(days=1)
            prev = rec._period_totals(prev_to - timedelta(days=days - 1), prev_to)

            invoices = self.env['account.move'].search([
                ('company_id', '=', rec.company_id.id),
                ('move_type', 'in', ('out_invoice', 'out_refund')),
                ('state', '=', 'posted'),
                ('invoice_date', '>=', rec.date_from), ('invoice_date', '<=', rec.date_to),
            ])
            revenue = sum(invoices.mapped('amount_untaxed_signed'))

            orders = self.env['purchase.order'].search([
                ('company_id', '=', rec.company_id.id),
                ('state', 'in', ('purchase', 'done')),
                ('date_order', '>=', fields.Datetime.to_datetime(rec.date_from)),
                ('date_order', '<', fields.Datetime.to_datetime(rec.date_to) + timedelta(days=1)),
            ])
            suppliers = orders.mapped('partner_id')
            evaluated = suppliers.filtered(lambda p: p.esg_last_date)

            total_t = cur['total'] / 1000.0
            prev_t = prev['total'] / 1000.0
            rec.write({
                'scope1_t': cur['s1'] / 1000.0,
                'scope2_t': cur['s2'] / 1000.0,
                'scope3_t': cur['s3'] / 1000.0,
                'total_t': total_t,
                'electricity_kwh': cur['elec'],
                'gas_kwh': cur['gas'],
                'revenue': revenue,
                'intensity': total_t / revenue * 1e6 if revenue else 0.0,
                'previous_total_t': prev_t,
                'change_pct': (total_t - prev_t) / prev_t * 100.0 if prev_t else 0.0,
                'target_gap_t': total_t - rec.target_total_t if rec.target_total_t else 0.0,
                'footprint_count': cur['count'],
                'supplier_count': len(suppliers),
                'supplier_evaluated_pct': len(evaluated) / len(suppliers) * 100.0 if suppliers else 0.0,
                'supplier_avg_esg': sum(evaluated.mapped('esg_score')) / len(evaluated) if evaluated else 0.0,
                'state': 'computed',
            })

    def action_publish(self):
        self.write({'state': 'published'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_print(self):
        self.ensure_one()
        return self.env.ref('carbon_footprint_management.action_report_carbon_report').report_action(self)
