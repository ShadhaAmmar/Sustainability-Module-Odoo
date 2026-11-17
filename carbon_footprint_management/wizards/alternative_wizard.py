# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class CarbonAlternativeWizard(models.TransientModel):
    _name = 'carbon.alternative.wizard'
    _description = "Alternatives écologiques"

    product_id = fields.Many2one('product.product', string="Produit actuel", required=True, readonly=True)
    current_intensity = fields.Float(related='product_id.carbon_intensity', string="Intensité actuelle (kg CO2e)")
    purchase_line_id = fields.Many2one('purchase.order.line', readonly=True)
    line_ids = fields.One2many('carbon.alternative.wizard.line', 'wizard_id', string="Alternatives")

    @api.model
    def _suggest_vals(self, product):
        Product = self.env['product.product']
        current = product.carbon_intensity
        declared = product.product_tmpl_id.eco_alternative_ids.mapped('product_variant_id')
        similar = Product
        if current > 0:
            similar = Product.search([
                ('id', '!=', product.id),
                ('categ_id', '=', product.categ_id.id),
                ('type', '=', product.type),
                ('carbon_intensity', '>', 0),
                ('carbon_intensity', '<', current),
            ], order='carbon_intensity asc', limit=10)
        vals = []
        for alt in (declared | similar) - product:
            seller = alt.seller_ids[:1].partner_id
            vals.append({
                'product_id': alt.id,
                'carbon_intensity': alt.carbon_intensity,
                'reduction_pct': (current - alt.carbon_intensity) / current * 100.0
                if current > 0 and alt.carbon_intensity > 0 else 0.0,
                'declared': alt in declared,
                'supplier_id': seller.id,
                'supplier_esg_score': seller.esg_score,
                'standard_price': alt.standard_price,
            })
        vals.sort(key=lambda v: -v['reduction_pct'])
        return vals

    @api.model
    def _open(self, product, purchase_line=None):
        if not product:
            raise UserError(_("Sélectionnez d'abord un produit."))
        wizard = self.create({
            'product_id': product.id,
            'purchase_line_id': purchase_line.id if purchase_line else False,
            'line_ids': [(0, 0, vals) for vals in self._suggest_vals(product)],
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _("Alternatives écologiques"),
            'res_model': self._name,
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }


class CarbonAlternativeWizardLine(models.TransientModel):
    _name = 'carbon.alternative.wizard.line'
    _description = "Ligne d'alternative écologique"
    _order = 'reduction_pct desc, id'

    wizard_id = fields.Many2one('carbon.alternative.wizard', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', string="Alternative", readonly=True)
    carbon_intensity = fields.Float("Intensité (kg CO2e)", digits=(16, 3), readonly=True)
    reduction_pct = fields.Float("Réduction (%)", digits=(16, 1), readonly=True)
    declared = fields.Boolean("Déclarée sur la fiche produit", readonly=True)
    supplier_id = fields.Many2one('res.partner', string="Fournisseur principal", readonly=True)
    supplier_esg_score = fields.Float("Score ESG fournisseur", digits=(16, 1), readonly=True)
    standard_price = fields.Float("Coût", readonly=True)

    def action_replace(self):
        self.ensure_one()
        line = self.wizard_id.purchase_line_id
        if not line:
            raise UserError(_("Aucune ligne d'achat associée."))
        if line.order_id.state not in ('draft', 'sent'):
            raise UserError(_("Seules les demandes de prix peuvent être modifiées."))
        line.product_id = self.product_id
        return {'type': 'ir.actions.act_window_close'}
