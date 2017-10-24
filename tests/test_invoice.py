# -*- coding: utf-8 -*-
import unittest
import datetime
from decimal import Decimal
from dateutil.relativedelta import relativedelta

import trytond.tests.test_tryton
from trytond.tests.test_tryton import (
    POOL, USER, CONTEXT,
    with_transaction, ModuleTestCase
)
from trytond.transaction import Transaction
from trytond.pyson import Eval


class TestInvoice(ModuleTestCase):
    """
    Invoice tests
    """

    module = 'invoice_payment_gateway'

    def setUp(self):
        """
        Set up data used in the tests.
        this method is called before each test function execution.
        """
        self.Currency = POOL.get('currency.currency')
        self.Company = POOL.get('company.company')
        self.Party = POOL.get('party.party')
        self.User = POOL.get('res.user')
        self.ProductTemplate = POOL.get('product.template')
        self.Uom = POOL.get('product.uom')
        self.ProductCategory = POOL.get('product.category')
        self.Product = POOL.get('product.product')
        self.Country = POOL.get('country.country')
        self.Subdivision = POOL.get('country.subdivision')
        self.Employee = POOL.get('company.employee')
        self.Journal = POOL.get('account.journal')
        self.Group = POOL.get('res.group')
        self.Country = POOL.get('country.country')
        self.Subdivision = POOL.get('country.subdivision')
        self.Invoice = POOL.get('account.invoice')
        self.PaymentGateway = POOL.get('payment_gateway.gateway')
        self.Sequence = POOL.get('ir.sequence')
        self.AccountConfiguration = POOL.get('account.configuration')

    def _create_fiscal_year(self, date=None, company=None):
        """
        Creates a fiscal year and requried sequences
        """
        FiscalYear = POOL.get('account.fiscalyear')
        Sequence = POOL.get('ir.sequence')
        SequenceStrict = POOL.get('ir.sequence.strict')
        Company = POOL.get('company.company')

        if date is None:
            date = datetime.date.today()

        if company is None:
            company, = Company.search([], limit=1)

        invoice_sequence, = SequenceStrict.create([{
            'name': '%s' % date.year,
            'code': 'account.invoice',
            'company': company,
        }])
        fiscal_year, = FiscalYear.create([{
            'name': '%s' % date.year,
            'start_date': date + relativedelta(month=1, day=1),
            'end_date': date + relativedelta(month=12, day=31),
            'company': company,
            'post_move_sequence': Sequence.create([{
                'name': '%s' % date.year,
                'code': 'account.move',
                'company': company,
            }])[0],
            'out_invoice_sequence': invoice_sequence,
            'in_invoice_sequence': invoice_sequence,
            'out_credit_note_sequence': invoice_sequence,
            'in_credit_note_sequence': invoice_sequence,
        }])
        FiscalYear.create_period([fiscal_year])
        return fiscal_year

    def _create_coa_minimal(self, company):
        """Create a minimal chart of accounts
        """
        AccountTemplate = POOL.get('account.account.template')
        Account = POOL.get('account.account')

        account_create_chart = POOL.get(
            'account.create_chart', type="wizard")

        account_template, = AccountTemplate.search([
            ('parent', '=', None),
            ('name', '=', 'Minimal Account Chart'),
        ])

        session_id, _, _ = account_create_chart.create()
        create_chart = account_create_chart(session_id)
        create_chart.account.account_template = account_template
        create_chart.account.company = company
        create_chart.transition_create_account()

        receivable, = Account.search([
            ('kind', '=', 'receivable'),
            ('company', '=', company),
        ])
        payable, = Account.search([
            ('kind', '=', 'payable'),
            ('company', '=', company),
        ])
        create_chart.properties.company = company
        create_chart.properties.account_receivable = receivable
        create_chart.properties.account_payable = payable
        create_chart.transition_create_properties()

    def _get_account_by_kind(self, kind, company=None, silent=True):
        """Returns an account with given spec
        :param kind: receivable/payable/expense/revenue
        :param silent: dont raise error if account is not found
        """
        Account = POOL.get('account.account')
        Company = POOL.get('company.company')

        if company is None:
            company, = Company.search([], limit=1)

        accounts = Account.search([
            ('kind', '=', kind),
            ('company', '=', company)
        ], limit=1)
        if not accounts and not silent:
            raise Exception("Account not found")
        return accounts[0] if accounts else False

    def _create_payment_term(self):
        """Create a simple payment term with all advance
        """
        PaymentTerm = POOL.get('account.invoice.payment_term')

        return PaymentTerm.create([{
            'name': 'Direct',
            'lines': [('create', [{'type': 'remainder'}])]
        }])

    def create_payment_profile(self, party, gateway):
        """
        Create a payment profile for the party
        """
        AddPaymentProfileWizard = POOL.get(
            'party.party.payment_profile.add', type='wizard'
        )

        # create a profile
        profile_wiz = AddPaymentProfileWizard(
            AddPaymentProfileWizard.create()[0]
        )
        profile_wiz.card_info.party = party.id
        profile_wiz.card_info.address = party.addresses[0].id
        profile_wiz.card_info.provider = gateway.provider
        profile_wiz.card_info.gateway = gateway
        profile_wiz.card_info.owner = party.name
        profile_wiz.card_info.number = '4111111111111111'
        profile_wiz.card_info.expiry_month = '11'
        profile_wiz.card_info.expiry_year = '2018'
        profile_wiz.card_info.csc = '353'

        with Transaction().set_context(return_profile=True):
            return profile_wiz.transition_add()

    def create_and_post_invoice(self, party):
        """
        Create and post an invoice for the party
        """
        Date = POOL.get('ir.date')

        with Transaction().set_context(company=self.company.id):
            invoice, = self.Invoice.create([{
                'party': party,
                'type': 'out',
                'journal': self.journal,
                'invoice_address': self.party.address_get(
                    'invoice'),
                'account': self._get_account_by_kind('receivable'),
                'description': 'Test Invoice',
                'payment_term': self.payment_term,
                'invoice_date': Date.today(),
                'lines': [('create', [{
                    'product': self.product1.id,
                    'description': self.product1.rec_name,
                    'quantity': 10,
                    'unit_price': Decimal('10.00'),
                    'unit': self.product1.default_uom,
                    'account': self.product1.account_revenue_used
                }, {
                    'product': self.product2.id,
                    'description': self.product2.rec_name,
                    'quantity': 10,
                    'unit_price': Decimal('20.00'),
                    'unit': self.product2.default_uom,
                    'account': self.product2.account_revenue_used
                }])]
            }])

        self.Invoice.post([invoice])
        return invoice

    def setup_defaults(self):
        """Creates default data for testing
        """
        currency, = self.Currency.create([{
            'name': 'US Dollar',
            'code': 'USD',
            'symbol': '$',
        }])

        with Transaction().set_context(company=None):
            company_party, = self.Party.create([{
                'name': 'Openlabs'
            }])

        self.company, = self.Company.create([{
            'party': company_party,
            'currency': currency,
        }])

        self.User.write([self.User(USER)], {
            'company': self.company,
            'main_company': self.company,
        })

        CONTEXT.update(self.User.get_preferences(context_only=True))

        # Create Fiscal Year
        self._create_fiscal_year(company=self.company.id)
        # Create Chart of Accounts
        self._create_coa_minimal(company=self.company.id)
        # Create a payment term
        self.payment_term, = self._create_payment_term()

        self.cash_journal, = self.Journal.search(
            [('type', '=', 'cash')], limit=1
        )

        # This is required to successfully pay the invoices
        main_cash_account = self._get_account_by_kind('other')

        self.Journal.write([self.cash_journal], {
            'debit_account': main_cash_account.id
        })

        self.uom, = self.Uom.search([('symbol', '=', 'd')])

        self.country, = self.Country.create([{
            'name': 'United States of America',
            'code': 'US',
        }])

        self.subdivision, = self.Subdivision.create([{
            'country': self.country.id,
            'name': 'California',
            'code': 'CA',
            'type': 'state',
        }])

        # Add address to company's party record
        self.Party.write([self.company.party], {
            'addresses': [('create', [{
                'name': 'Openlabs',
                'party': Eval('id'),
                'city': 'Los Angeles',
                'invoice': True,
                'country': self.country.id,
                'subdivision': self.subdivision.id,
            }])],
        })

        # Create party
        self.party, = self.Party.create([{
            'name': 'Bruce Wayne',
            'addresses': [('create', [{
                'name': 'Bruce Wayne',
                'party': Eval('id'),
                'city': 'Gotham',
                'invoice': True,
                'country': self.country.id,
                'subdivision': self.subdivision.id,
            }])],
            'customer_payment_term': self.payment_term.id,
            'account_receivable': self._get_account_by_kind(
                'receivable').id,
            'contact_mechanisms': [('create', [
                {'type': 'mobile', 'value': '8888888888'},
            ])],
        }])

        self.journal, = self.Journal.search([('type', '=', 'revenue')], limit=1)

        self.product_category, = self.ProductCategory.create([{
            'name': 'Test Category',
            'account_revenue': self._get_account_by_kind(
                'revenue', company=self.company.id).id,
            'account_expense': self._get_account_by_kind(
                'expense', company=self.company.id).id,
        }])

        self.product_template, = self.ProductTemplate.create([{
            'name': 'Toy',
            'type': 'goods',
            'list_price': Decimal('10'),
            'cost_price': Decimal('5'),
            'categories': [('add', [self.product_category.id])],
            'default_uom': self.uom,
            'account_revenue': self._get_account_by_kind(
                'revenue', company=self.company.id).id,
            'account_expense': self._get_account_by_kind(
                'expense', company=self.company.id).id,
        }])

        self.product1, = self.Product.create([{
            'template': self.product_template.id,
            'code': 'toy-1',
        }])
        self.product2, = self.Product.create([{
            'template': self.product_template.id,
            'code': 'toy-2',
        }])

        with Transaction().set_context(use_dummy=True):
            self.dummy_gateway, = self.PaymentGateway.create([{
                'name': 'Dummy Gateway',
                'journal': self.cash_journal.id,
                'provider': 'dummy',
                'method': 'credit_card',
            }])
        self.dummy_cc_payment_profile = self.create_payment_profile(
            self.party, self.dummy_gateway
        )

        self.cash_gateway, = self.PaymentGateway.create([{
            'name': 'Cash Gateway',
            'journal': self.cash_journal.id,
            'provider': 'self',
            'method': 'manual',
        }])

        # Create and set write-off journal
        write_off_journal, = self.Journal.create([{
            'name': 'Write-Off',
            'type': 'write-off',
            'credit_account': self._get_account_by_kind(
                'revenue', company=self.company.id).id,
            'debit_account': self._get_account_by_kind(
                'expense', company=self.company.id).id,
            'sequence': self.Sequence.search([
                ('code', '=', 'account.journal')
            ])[0].id
        }])
        account_config = self.AccountConfiguration(1)
        account_config.write_off_journal = write_off_journal
        account_config.save()

    @with_transaction()
    def test_0010_test_paying_invoice_with_cash(self):
        """
        Create and pay an invoice using payment transaction
        """
        self.setup_defaults()

        invoice = self.create_and_post_invoice(self.party)

        self.assertTrue(invoice)
        self.assertEqual(invoice.state, 'posted')
        self.assertTrue(invoice.amount_to_pay)

        # Pay invoice using cash transaction
        Wizard = POOL.get(
            'account.invoice.pay_using_transaction', type='wizard'
        )
        with Transaction().set_context(active_id=invoice.id):
            pay_wizard = Wizard(Wizard.create()[0])
            defaults = pay_wizard.default_start()

            pay_wizard.start.invoice = defaults['invoice']
            pay_wizard.start.party = defaults['party']
            pay_wizard.start.company = defaults['company']
            pay_wizard.start.credit_account = defaults['credit_account']
            pay_wizard.start.owner = defaults['owner']
            pay_wizard.start.currency_digits = defaults['currency_digits']
            pay_wizard.start.amount = defaults['amount']
            pay_wizard.start.user = defaults['user']
            pay_wizard.start.gateway = self.cash_gateway.id
            pay_wizard.start.payment_profile = None
            pay_wizard.start.reference = 'Test paying with cash'
            pay_wizard.start.method = self.cash_gateway.method
            pay_wizard.start.transaction_type = defaults['transaction_type']

            with Transaction().set_context(company=self.company.id):
                pay_wizard.transition_pay()

        self.assertEqual(invoice.state, 'paid')
        self.assertFalse(invoice.amount_to_pay)

    @with_transaction()
    def test_0020_test_paying_invoice_with_new_credit_card(self):
        """
        Create and pay an invoice using payment transaction
        """
        Date = POOL.get('ir.date')

        self.setup_defaults()

        invoice = self.create_and_post_invoice(self.party)

        self.assertTrue(invoice)
        self.assertEqual(invoice.state, 'posted')
        self.assertTrue(invoice.amount_to_pay)

        # Pay invoice using cash transaction
        Wizard = POOL.get(
            'account.invoice.pay_using_transaction', type='wizard'
        )
        with Transaction().set_context(active_id=invoice.id):
            pay_wizard = Wizard(Wizard.create()[0])
            defaults = pay_wizard.default_start()

            pay_wizard.start.invoice = defaults['invoice']
            pay_wizard.start.party = defaults['party']
            pay_wizard.start.company = defaults['company']
            pay_wizard.start.credit_account = defaults['credit_account']
            pay_wizard.start.owner = defaults['owner']
            pay_wizard.start.currency_digits = defaults['currency_digits']
            pay_wizard.start.amount = defaults['amount']
            pay_wizard.start.user = defaults['user']
            pay_wizard.start.gateway = self.dummy_gateway.id
            pay_wizard.start.payment_profile = None
            pay_wizard.start.reference = 'Test paying with cash'
            pay_wizard.start.method = self.dummy_gateway.method
            pay_wizard.start.use_existing_card = False
            pay_wizard.start.number = '4111111111111111'
            pay_wizard.start.expiry_month = '05'
            pay_wizard.start.expiry_year = '%s' % (Date.today().year + 3)
            pay_wizard.start.csc = '435'
            pay_wizard.start.provider = self.dummy_gateway.provider
            pay_wizard.start.transaction_type = defaults['transaction_type']

            with Transaction().set_context(company=self.company.id):
                pay_wizard.transition_pay()

        self.assertEqual(invoice.state, 'paid')
        self.assertFalse(invoice.amount_to_pay)

    @with_transaction()
    def test_0030_test_paying_invoice_with_saved_credit_card(self):
        """
        Create and pay an invoice using payment transaction
        """
        self.setup_defaults()

        invoice = self.create_and_post_invoice(self.party)

        self.assertTrue(invoice)
        self.assertEqual(invoice.state, 'posted')
        self.assertTrue(invoice.amount_to_pay)

        # Pay invoice using cash transaction
        Wizard = POOL.get(
            'account.invoice.pay_using_transaction', type='wizard'
        )
        with Transaction().set_context(active_id=invoice.id):
            pay_wizard = Wizard(Wizard.create()[0])
            defaults = pay_wizard.default_start()

            pay_wizard.start.invoice = defaults['invoice']
            pay_wizard.start.party = defaults['party']
            pay_wizard.start.company = defaults['company']
            pay_wizard.start.credit_account = defaults['credit_account']
            pay_wizard.start.owner = defaults['owner']
            pay_wizard.start.currency_digits = defaults['currency_digits']
            pay_wizard.start.amount = defaults['amount']
            pay_wizard.start.user = defaults['user']
            pay_wizard.start.gateway = self.dummy_gateway.id
            pay_wizard.start.payment_profile = \
                self.dummy_cc_payment_profile.id
            pay_wizard.start.reference = 'Test paying with cash'
            pay_wizard.start.method = self.dummy_gateway.method
            pay_wizard.start.use_existing_card = True
            pay_wizard.start.transaction_type = defaults['transaction_type']

            with Transaction().set_context(company=self.company.id):
                pay_wizard.transition_pay()

        self.assertEqual(invoice.state, 'paid')
        self.assertFalse(invoice.amount_to_pay)

    @with_transaction()
    def test_0040_test_paying_invoice_write_off(self):
        """Test invoice pay logic with write-off.
        """
        self.setup_defaults()

        account_config = self.AccountConfiguration(1)
        self.assertEqual(
            account_config.write_off_threshold, Decimal('0')
        )

        invoice = self.create_and_post_invoice(self.party)

        self.assertTrue(invoice)
        self.assertEqual(invoice.state, 'posted')
        self.assertTrue(invoice.amount_to_pay)

        # Pay invoice using cash transaction
        Wizard = POOL.get(
            'account.invoice.pay_using_transaction', type='wizard'
        )
        with Transaction().set_context(active_id=invoice.id):
            pay_wizard = Wizard(Wizard.create()[0])
            defaults = pay_wizard.default_start()

            pay_wizard.start.invoice = defaults['invoice']
            pay_wizard.start.party = defaults['party']
            pay_wizard.start.company = defaults['company']
            pay_wizard.start.credit_account = defaults['credit_account']
            pay_wizard.start.owner = defaults['owner']
            pay_wizard.start.currency_digits = defaults['currency_digits']
            pay_wizard.start.amount = defaults['amount'] - Decimal('0.02')
            pay_wizard.start.user = defaults['user']
            pay_wizard.start.gateway = self.cash_gateway.id
            pay_wizard.start.payment_profile = None
            pay_wizard.start.reference = 'Test paying with cash'
            pay_wizard.start.method = self.cash_gateway.method
            pay_wizard.start.transaction_type = defaults['transaction_type']

            with Transaction().set_context(company=self.company.id):
                pay_wizard.transition_pay()

        self.assertEqual(invoice.state, 'posted')
        self.assertTrue(invoice.amount_to_pay)

        # Set the write-off threshold and pay invoice again.
        with Transaction().set_context(active_id=invoice.id):
            pay_wizard = Wizard(Wizard.create()[0])
            defaults = pay_wizard.default_start()

            pay_wizard.start.invoice = defaults['invoice']
            pay_wizard.start.party = defaults['party']
            pay_wizard.start.company = defaults['company']
            pay_wizard.start.credit_account = defaults['credit_account']
            pay_wizard.start.owner = defaults['owner']
            pay_wizard.start.currency_digits = defaults['currency_digits']
            pay_wizard.start.amount = defaults['amount']
            pay_wizard.start.user = defaults['user']
            pay_wizard.start.gateway = self.cash_gateway.id
            pay_wizard.start.payment_profile = None
            pay_wizard.start.reference = 'Test paying with cash'
            pay_wizard.start.method = self.cash_gateway.method
            pay_wizard.start.transaction_type = defaults['transaction_type']

            with Transaction().set_context(company=self.company.id):
                pay_wizard.transition_pay()

        self.assertEqual(invoice.state, 'paid')
        self.assertFalse(invoice.amount_to_pay)


def suite():
    "Define suite"
    test_suite = trytond.tests.test_tryton.suite()
    test_suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestInvoice)
    )
    return test_suite


if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
