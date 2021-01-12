# Copyright 2021 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from .common import Common


class TestCreateIndexesLine(Common):
    def setUp(self):
        super(TestCreateIndexesLine, self).setUp()
        # delete some index and check if our module recreated it
        self.env.cr.execute("drop index res_partner_name_index")

    def test_purge(self):
        wizard = self.env["cleanup.create_indexes.wizard"].create({})
        wizard.purge_all()
        self.env.cr.execute(
            "select indexname from pg_indexes "
            "where indexname='res_partner_name_index' and "
            "tablename='res_partner'"
        )
        self.assertEqual(self.env.cr.rowcount, 1)
