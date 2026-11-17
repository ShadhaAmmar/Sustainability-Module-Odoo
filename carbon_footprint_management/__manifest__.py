# -*- coding: utf-8 -*-
{
    'name': 'Durabilité & Empreinte Carbone',
    'version': '17.0.1.0.0',
    'category': 'Sustainability',
    'summary': "Empreinte carbone, scoring ESG fournisseurs, rapports CSRD/ESRS E1, certificats carbone",
    'description': """
Durabilité & Empreinte Carbone
==============================
* Calcul automatique de l'empreinte carbone par commande d'achat, de vente et ordre de fabrication
* Intensité carbone par produit, calculable depuis la nomenclature (Manufacturing)
* Scoring ESG des fournisseurs (E / S / G) avec alerte à l'achat
* Rapports de durabilité structurés selon ESRS E1 (CSRD) et GHG Protocol
* Suggestions d'alternatives écologiques (remplacement direct sur la ligne d'achat)
* Certificats carbone imprimables pour les clients
    """,
    'author': 'Shoushou',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'product', 'stock', 'purchase', 'sale', 'mrp', 'account'],
    'data': [
        'security/carbon_security.xml',
        'security/ir.model.access.csv',
        'data/carbon_data.xml',
        'data/esg_data.xml',
        'views/carbon_footprint_views.xml',
        'views/carbon_certificate_views.xml',
        'views/esg_views.xml',
        'views/carbon_report_views.xml',
        'views/inherit_views.xml',
        'wizards/alternative_wizard_views.xml',
        'report/carbon_certificate_report.xml',
        'report/carbon_report_template.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
