import json
import sys
from datetime import date

from bx_report.src.database import DBConnection, InterfaceAuthMod
from bx_report.src.utils.BXTool import BXTool
from utils.Utilsdate import Utilsdate


class BXLoader(DBConnection, InterfaceAuthMod):
    # bound with class, like static variable in Java
    BEGINNING_DATE = date(2016, 1, 1)

    def __init__(self, host, port, user, password, dbname,
                 bx_login, bx_pw, schema='public', billing_table='billing',
                 auth_table='authentication',
                 api_uk="https://api.eu-gb.bluemix.net",
                 api_us="https://api.ng.bluemix.net",
                 api_au="https://api.au-syd.bluemix.net",
                 beginning_date=None):

        super(BXLoader, self).__init__(host, port, user, password, dbname,
                                       schema, billing_table, auth_table)

        self.beginning_date = beginning_date if beginning_date \
            else BXLoader.BEGINNING_DATE

        self.loaded_region = list()

        self.CREATE_BILLING_TABLE_STATEMENT = """
            CREATE TABLE IF NOT EXISTS %s.%s(
                region character varying NOT NULL,
                organization character varying NOT NULL,
                space character varying NOT NULL,
                date character varying NOT NULL,
                applications json,
                containers json,
                services json,
                CONSTRAINT billing_pkey PRIMARY KEY (region, organization, space, date)
            );""" % (self.schema, self.billing_table)

        self.bx_tool = BXTool(bx_login, bx_pw, api_uk, api_us, api_au)

        try:
            self.__create_billing_table()
        except:
            print >> sys.stderr, "create billing table error."

    # inherits __del__ of superclass

    def __create_billing_table(self):
        self.cursor.execute(self.CREATE_BILLING_TABLE_STATEMENT)
        self.conn.commit()
        self.logger.debug('Table {}.{} created.'.format(self.schema, self.billing_table))

    def load_all_region(self, starting_date):

        self.bx_tool.CFLogin('uk')
        self.__load_current_region(starting_date)
        self.bx_tool.CFLogin('us')
        self.__load_current_region(starting_date)
        self.bx_tool.CFLogin('au')
        self.__load_current_region(starting_date)

        self.conn.commit()

    def __load_current_region(self, beginning_date):
        '''
        load billing info to factory for an organization of a region
        :param region:
        :param org:
        :param space:
        :param beginning_date:
        :return:
        '''
        if (self.bx_tool.connected_region and
                (self.bx_tool.connected_region not in self.loaded_region)):

            report_date = date.today()

            while (report_date >= beginning_date):
                report_date_str = Utilsdate.stringnize_date(report_date)
                org_list = self.bx_tool.get_orgs_list_by_date(report_date_str)
                for org in org_list:
                    bill_records = self.bx_tool.retrieve_records(org, report_date_str)
                    if bill_records:
                        for record in bill_records:
                            if self._check_existence(record["region"], org, record["space"], record["date"]):
                                if report_date.year == date.today().year and report_date.month == date.today().month:
                                    self._update_record(record["region"], org, record["space"], record["date"],
                                                        json.dumps(record["applications"]),
                                                        json.dumps(record["containers"]),
                                                        json.dumps(record["services"]))
                                else:
                                    break
                            else:
                                self._insert_record(record["region"], org, record["space"], record["date"],
                                                    json.dumps(record["applications"]),
                                                    json.dumps(record["containers"]),
                                                    json.dumps(record["services"]))
                report_date = Utilsdate.previous_month_date(report_date)
            self.loaded_region.append(self.bx_tool.connected_region)
            self.logger.info('Region {} loaded.'.format(self.bx_tool.connected_region))
        else:
            self.logger.info('Region {} already loaded, loading skipped.'.format(self.bx_tool.connected_region))

    def _check_existence(self, region, org, space, date):
        SELECT_STATEMENT = self._select(
            '*', self.schema, self.billing_table, region=region,
            organization=org, space=space, date=date)
        self.cursor.execute(SELECT_STATEMENT)
        if self.cursor.fetchone():
            return True
        else:
            return False

    def _update_record(self, region, org, space, date, applications, containers, services):
        UPDATE_STATEMENT = """
            UPDATE %s.%s
            SET applications='%s', containers='%s', services='%s'
            WHERE region = '%s' AND organization = '%s' AND space = '%s' AND date = '%s';
            """ % (self.schema, self.billing_table, applications,
                   containers, services, region, org, space, date)
        try:
            self.cursor.execute(UPDATE_STATEMENT)
        except:
            self.logger.debug('EXCEPTION in update.')
        self.conn.commit()

    def _insert_record(self, region, org, space, date, applications, containers, services):
        INSERT_STATEMENT = """
            INSERT INTO %s.%s
            (region, organization, space, date, applications, containers, services)
            VALUES ('%s', '%s', '%s', '%s', '%s', '%s', '%s');
            """ % (self.schema, self.billing_table,
                   region, org, space, date, applications, containers, services)
        self.cursor.execute(INSERT_STATEMENT)
        self.conn.commit()
