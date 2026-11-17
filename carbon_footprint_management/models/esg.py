# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

ESG_CATEGORIES = [
    ('environmental', 'Environnement (E)'),
    ('social', 'Social (S)'),
    ('governance', 'Gouvernance (G)'),
]
ESG_WEIGHTS = {'environmental': 0.4, 'social': 0.3, 'governance': 0.3}
ESG_RATINGS = [
    ('a', 'A – Excellent'),
    ('b', 'B – Bon'),
    ('c', 'C – Moyen'),
    ('d', 'D – Faible'),
    ('e', 'E – Critique'),
]


def rating_from_score(score):
    if score >= 80:
        return 'a'
    if score >= 65:
        return 'b'
    if score >= 50:
        return 'c'
    if score >= 35:
        return 'd'
    return 'e'


class EsgCriteria(models.Model):
    _name = 'esg.criteria'
    _description = "Critère ESG"
    _order = 'category, sequence, id'

    name = fields.Char("Critère", required=True, translate=True)
    code = fields.Char("Code")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    category = fields.Selection(ESG_CATEGORIES, string="Pilier", required=True)
    weight = fields.Float("Pondération", default=1.0)
    description = fields.Text("Guide d'évaluation", translate=True)


class EsgScoring(models.Model):
    _name = 'esg.scoring'
    _description = "Évaluation ESG fournisseur"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char("Référence", required=True, copy=False, readonly=True, default=lambda self: _('New'))
    partner_id = fields.Many2one('res.partner', string="Fournisseur", required=True, tracking=True)
    date = fields.Date("Date d'évaluation", required=True, default=fields.Date.context_today, tracking=True)
    evaluator_id = fields.Many2one('res.users', string="Évaluateur", default=lambda self: self.env.user)
    company_id = fields.Many2one('res.company', string="Société", required=True,
                                 default=lambda self: self.env.company)
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('validated', 'Validée'),
        ('cancelled', 'Annulée'),
    ], default='draft', required=True, tracking=True, copy=False)
    line_ids = fields.One2many('esg.scoring.line', 'scoring_id', string="Critères", copy=True)
    environmental_score = fields.Float("Score E", compute='_compute_scores', store=True, digits=(16, 1))
    social_score = fields.Float("Score S", compute='_compute_scores', store=True, digits=(16, 1))
    governance_score = fields.Float("Score G", compute='_compute_scores', store=True, digits=(16, 1))
    total_score = fields.Float("Score ESG global", compute='_compute_scores', store=True,
                               digits=(16, 1), tracking=True)
    rating = fields.Selection(ESG_RATINGS, string="Note ESG", compute='_compute_scores', store=True)
    notes = fields.Text("Observations / plan d'amélioration")

    @api.depends('line_ids.score', 'line_ids.weight', 'line_ids.category')
    def _compute_scores(self):
        for rec in self:
            scores = {}
            for cat, _label in ESG_CATEGORIES:
                lines = rec.line_ids.filtered(lambda l, cat=cat: l.category == cat)
                weight = sum(lines.mapped('weight'))
                if weight:
                    scores[cat] = sum(l.score * l.weight for l in lines) / weight
            total_weight = sum(ESG_WEIGHTS[c] for c in scores)
            total = sum(scores[c] * ESG_WEIGHTS[c] for c in scores) / total_weight if total_weight else 0.0
            rec.environmental_score = scores.get('environmental', 0.0)
            rec.social_score = scores.get('social', 0.0)
            rec.governance_score = scores.get('governance', 0.0)
            rec.total_score = total
            rec.rating = rating_from_score(total)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('esg.scoring') or _('New')
        records = super().create(vals_list)
        for rec in records.filtered(lambda r: not r.line_ids):
            rec._load_criteria()
        return records

    def _load_criteria(self):
        self.ensure_one()
        criteria = self.env['esg.criteria'].search([])
        self.write({'line_ids': [(0, 0, {
            'criteria_id': c.id,
            'name': c.name,
            'category': c.category,
            'weight': c.weight,
        }) for c in criteria]})

    def action_load_criteria(self):
        for rec in self:
            existing = rec.line_ids.mapped('criteria_id')
            for c in self.env['esg.criteria'].search([('id', 'not in', existing.ids)]):
                rec.write({'line_ids': [(0, 0, {
                    'criteria_id': c.id, 'name': c.name, 'category': c.category, 'weight': c.weight,
                })]})

    def action_validate(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_("Ajoutez des critères avant de valider l'évaluation."))
            rec.state = 'validated'

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_draft(self):
        self.write({'state': 'draft'})


class EsgScoringLine(models.Model):
    _name = 'esg.scoring.line'
    _description = "Ligne d'évaluation ESG"
    _order = 'category, id'

    scoring_id = fields.Many2one('esg.scoring', required=True, ondelete='cascade')
    criteria_id = fields.Many2one('esg.criteria', string="Critère de référence")
    name = fields.Char("Critère", required=True)
    category = fields.Selection(ESG_CATEGORIES, string="Pilier", required=True)
    weight = fields.Float("Pondération", default=1.0)
    score = fields.Float("Score (0-100)")
    evidence = fields.Char("Preuve / commentaire")

    @api.constrains('score')
    def _check_score(self):
        for line in self:
            if not 0 <= line.score <= 100:
                raise ValidationError(_("Le score doit être compris entre 0 et 100."))

    @api.constrains('weight')
    def _check_weight(self):
        for line in self:
            if line.weight < 0:
                raise ValidationError(_("La pondération ne peut pas être négative."))


class ResPartner(models.Model):
    _inherit = 'res.partner'

    esg_scoring_ids = fields.One2many('esg.scoring', 'partner_id', string="Évaluations ESG")
    esg_scoring_count = fields.Integer(compute='_compute_esg_scoring_count')
    esg_score = fields.Float("Score ESG", compute='_compute_esg', store=True, digits=(16, 1))
    esg_rating = fields.Selection(ESG_RATINGS, string="Note ESG", compute='_compute_esg', store=True)
    esg_last_date = fields.Date("Dernière évaluation ESG", compute='_compute_esg', store=True)

    @api.depends('esg_scoring_ids')
    def _compute_esg_scoring_count(self):
        for partner in self:
            partner.esg_scoring_count = len(partner.sudo().esg_scoring_ids)

    @api.depends('esg_scoring_ids.state', 'esg_scoring_ids.total_score', 'esg_scoring_ids.date')
    def _compute_esg(self):
        for partner in self:
            valid = partner.esg_scoring_ids.filtered(lambda s: s.state == 'validated')
            last = valid.sorted(key=lambda s: (s.date, s.id), reverse=True)[:1]
            partner.esg_score = last.total_score if last else 0.0
            partner.esg_rating = last.rating if last else False
            partner.esg_last_date = last.date if last else False

    def action_new_esg_scoring(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Nouvelle évaluation ESG"),
            'res_model': 'esg.scoring',
            'view_mode': 'form',
            'context': {'default_partner_id': self.id},
        }
