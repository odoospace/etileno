# -*- coding: utf-8 -*-

import base64
from lxml import etree
from openerp import models, fields, api
import coredb

F = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j']

class etileno_source(models.Model):
    _name = 'etileno.source'

    @api.one
    def verify_connection(self):
        db = coredb.DB(self.source_type, data=self.data)
        conn = db.connect(self.host, self.port, self.database, self.username, self.password)
        if conn:
            self.state = 'verified'

    @api.one
    def refresh(self):
        db = coredb.DB(self.source_type, data=self.data)
        conn = db.connect(self.host, self.port, self.database, self.username, self.password)
        if not conn:
            raise Exception("I can't connect with this source: %s" % self.name)
        for table in self.table_ids:
            print 'Refreshing %s...' % table.name
            data = {
                'rows': db.refresh(table.name)
            }
            print data
            table.write(data)


    @api.one
    def introspection(self):
        """get structure from source and create tables and fields in etileno"""
        db = coredb.DB(self.source_type, data=self.data)
        conn = db.connect(self.host, self.port, self.database, self.username, self.password)
        tables = db.show_tables()
        table = self.env['etileno.table']
        for k,v in tables.items():
            print v
            # get fields
            fields = []
            for i in v['fields']:
                fields.append((0,0, {
                    'name': i[0],
                    'field_type': i[1],
                    'pk': i[0] in v['pk'] and (v['pk'].index(i[0]) + 1)
                }))
            # create table and fields
            data = {
                'source_id': self.id,
                'name': k,
                'rows': v['count'],
                'field_ids': fields
            }
            table.create(data)


    @api.onchange('source_type')
    def _onchange_source_type_(self):
        # check if empty
        if self.source_type:
            self.port = coredb.modules[self.source_type]['port']
        else:
            self.port = None

    @api.model
    def create(self, vals):
        vals['state'] = 'draft' # add default state value here
        res = super(etileno_source, self).create(vals)
        return res


    # TODO: add tunel ssh info and connection string
    name = fields.Char(required=True)
    source_type = fields.Selection(coredb.engines, string='Source type', default=coredb.engines[0][0], required=True)
    filename = fields.Char()
    data = fields.Binary() # for CSV, etc.
    host = fields.Char(default='127.0.0.1', required=True)
    port = fields.Integer()
    database = fields.Char()
    username = fields.Char()
    password = fields.Char()
    table_ids = fields.One2many('etileno.table', 'source_id')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('verified', 'Verified'),
        ('instrospection', 'Introspection'),
        ('sync', 'Sync'),
        ('done', 'Done')
    ])


class etileno_table(models.Model):
    _name = 'etileno.table'

    @api.multi
    def action_name (self):
        view = self.env.ref('etileno.view_etileno_table_form').id
        return {
            'type': 'ir.actions.act_windows',
            'res_id': self.id
        }

    @api.multi
    def reload_page(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',  }

        model_obj = self.env['ir.model.data']
        data_id = model_obj._get_id('etileno', 'view_etileno_table_form')
        view_id = model_obj.browse(data_id).res_id
        return {
            'type': 'ir.actions.act_window',
            'name': 'String',
            'res_model': 'model.name',
            'view_type' : 'form',
            'view_mode' : 'form',
            'view_id' : view_id,
            'target' : 'current',
            'nodestroy' : True,
        }

    @api.model
    def fields_view_get(self, view_id=None, view_type='tree', context=None, toolbar=False, submenu=False):
        res = super(etileno_table, self).fields_view_get(view_id=view_id, view_type=view_type, context=self.env.context, toolbar=toolbar, submenu=submenu)
        if self.env.context.has_key('params'):
            params = self.env.context['params']
            if view_type == 'form' and params.get('view_type', None) == 'form' and params['model'] == 'etileno.table':
                id = self.env.context['params']['id']
                # check if fields < visible columns to show
                if self.env['etileno.field'].search_count([('table_id', '=', id)]) <= 10:
                    fields = [i.name for i in self.env['etileno.field'].search([('table_id', '=', id)])]
                else:
                    fields = [i.name for i in self.env['etileno.field'].search([('table_id', '=', id), ('visible', '=', True)])]
                if fields:
                    print fields
                    t = res['fields']['row_ids']['views']['tree']['arch']
                    for i in xrange(10):
                        if i < len(fields):
                            t = t.replace('#%s#' % F[i], fields[i])
                        else:
                            t = t.replace('#%s#' % F[i], '')
                    res['fields']['row_ids']['views']['tree']['arch'] = t
        return res

    @api.one
    def _get_rows_related(self):
        if self.env['etileno.field'].search_count([('table_id', '=', self.id)]) <= 10:
            fields = [i.name for i in self.env['etileno.field'].search([('table_id', '=', self.id)])]
        else:
            fields = [i.name for i in self.env['etileno.field'].search([('table_id', '=', self.id), ('visible', '=', True)])]
        if fields:
            # TODO: to keep simple connections
            db = coredb.DB(self.source_id.source_type)
            conn = db.connect(self.source_id.host, self.source_id.port, self.source_id.database, self.source_id.username, self.source_id.password)
            rows = db.get_data(self.name, fields)

            # add column name
            #data = dict([(F[i], fields[i]) for i in xrange(len(fields))])
            #self.row_ids |= self.env['etileno.row'].create(data)

            # add data rows
            for row in rows:
                data = {}
                for i in xrange(len(fields)):
                    data[F[i]] = row[fields[i]]
                self.row_ids |= self.env['etileno.row'].create(data)

    @api.one
    def _get_pks(self):
        f = []
        for field in self.field_ids:
            if field.pk > 0:
                f.append(field.name)
        if f:
            res = ','.join(f)
            self.pks = len(res) < 24 and res or res[:24] + '...'
        else:
            self.pks = '' # empty

    source_id = fields.Many2one('etileno.source', 'Source')
    field_ids = fields.One2many('etileno.field', 'table_id', 'Fields')
    translate_ids = fields.One2many('etileno.table.translate', 'table_id')
    source_type = fields.Selection(related='source_id.source_type', string='DB Type', store=True, readonly=True)
    name = fields.Char()
    rows = fields.Integer()
    row_ids = fields.One2many('etileno.row', 'table_id', string='Rows', compute='_get_rows_related')
    model = fields.Many2one('ir.model') # default model to map
    info = fields.Text()
    pks = fields.Char(compute='_get_pks') # pk fields separeted by commas


class etileno_field(models.Model):
    _name = 'etileno.field'

    #@api.model
    #def fields_view_get(self, view_id=None, view_type='tree', context=None, toolbar=False, submenu=False):
    #    res = super(etileno_field,self).fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)
    #    return res

    table_id = fields.Many2one('etileno.table', 'Table', readonly=True)
    source = fields.Many2one(related='table_id.source_id', store=True, readonly=True)
    name = fields.Char()
    field_type = fields.Char('Type')
    pk = fields.Integer('PK') # primary key order (1, 2, 3...)
    visible = fields.Boolean()
    fk_id = fields.Many2one('etileno.field')
    fk_child_ids = fields.One2many('etileno.field', 'fk_id')
    fk_table_id = fields.Many2one('etileno.table')
    fk_fields = fields.Char() # separated by commas fields


class etileno_task_action(models.Model):
    # TODO: basic constaint - it need its own model
    # TODO: check for primary keys to create data
    _name = 'etileno.task.action'

    order = fields.Integer()
    translate_id = fields.Many2one('etileno.table.translate')
    task_id = fields.Many2one('etileno.task')
    source = fields.Many2one(related='field_id.source', readonly=True)
    table = fields.Many2one(related='field_id.table_id', readonly=True)
    field_id = fields.Many2one('etileno.field')
    odoo_model = fields.Many2one(related='odoo_field_id.model_id', readonly=True)
    odoo_field_id = fields.Many2one('ir.model.fields')
    action = fields.Selection([
        ('c', 'copy'),
        ('sr', 'search & replace'),
        ('r', 'replace'),
        ('C', 'check'), # check if exist
        ('R', 'related'), # get related value (use foreign keys)
        ('pk', 'primary key'),
    ], default='c')
    action_value = fields.Char() # until 126 bytes
    transform = fields.Text() # python code to eval (alpha)


class etileno_task_log(models.Model):
    """keep pk values from actions to track tasks"""
    _name = 'etileno.task.log'

    task_id = fields.Many2one('etileno.task')
    table_row_pk = fields.Char()
    model_row_pk = fields.Char()


class etileno_task(models.Model):
    _name = 'etileno.task'

    @api.multi
    def run_task(self):
        # TODO: add log / pk
        source = {}
        #data = {}
        fields = []

        # group fields by table
        for i in self.task_action_ids:
            if not source.has_key(i.source):
                source[i.source] = []
            source[i.source].append(i)

        for source, actions in source.items():
            if source.source_type == 'csv':
                db = coredb.DB(source.source_type, data=source.data)
                conn = db.connect()
                rows = db.get_rows()
                for row in rows.dicts():
                    # d = {model: {data fields}}
                    d = {}
                    for action in actions:
                        if not d.has_key(action.odoo_model.model):
                            d[action.odoo_model.model] = {}
                        d[action.odoo_model.model][action.odoo_field_id.name] = row[action.field_id.name]

                    for model, data in d.items():
                        self.env[model].create(data)
            elif source.source_type in ['pymssql', 'psycopg2']:
                # get tables and fields
                tables = {}
                for action in actions:
                    if not tables.has_key(action.table.name):
                        tables[action.table.name] = []
                    tables[action.table.name].append(action.field_id.name)

                # connect with database
                db = coredb.DB(source.source_type)
                conn = db.connect(source.host, source.port, source.database, source.username, source.password)
                if not conn:
                    print 'ERROR'

                # get rows from tables
                for table, fields in tables.items():
                    #print table, fields
                    rows = db.get_rows(table=table, fields=fields)

                    for row in rows:
                        #print row
                        d = {}
                        create = True
                        for action in actions:
                            # prepare data for create
                            if action.action in ['c', 'cr']:
                                if not d.has_key(action.odoo_model.model):
                                    d[action.odoo_model.model] = {}

                            # checks
                            if action.action == 'pk': # primary key
                                field_pk = row[action.field_id.name]
                            elif action.action == 'C': # check value
                                print '>', row[action.field_id.name], action.action_value
                                # TODO: cast action_value right
                                if not row[action.field_id.name] == int(action.action_value):
                                    create = False
                            elif action.action == 'c': # create
                                d[action.odoo_model.model][action.odoo_field_id.name] = row[action.field_id.name]

                        print '+++', create, d
                        # create register
                        if create:
                            for model, data in d.items():
                                #print model, data
                                pk_id = self.env[model].create(data)
                                log_data = {
                                    'task_id': self.id,
                                    'table_row_pk': field_pk,
                                    'model_row_pk': pk_id
                                }
                                self.env['etileno.task.log'].create(log_data)


    name = fields.Char()
    task_action_ids = fields.One2many('etileno.task.action', 'task_id')
    table_id = fields.Many2one('etileno.table') # default table for actions
    odoo_model_id = fields.Many2one('ir.model') # default model for actions
    constraint = fields.Char() # eval this to perform an action... (alpha)


class etileno_table_translate(models.Model):
    _name = 'etileno.table.translate'

    @api.one
    def search_match(self):
        rows = {}

        # get codes from source
        db = coredb.DB(self.source.source_type, data=self.source.data)
        conn = db.connect(self.source.host, self.source.port, self.source.database, self.source.username, self.source.password)
        if not conn:
            raise Exception("I can't connect with this source: %s" % self.name)
        rows_source = db.get_rows(table=self.table_id.name, fields=self.table_id.pks.split(',') + [self.field_match_id.name])
        for row in rows_source:
            #print '>>', row
            if rows.has_key(row[-1]) or row[-1] == None:
                if self.test:
                    raise Exception("Code repeated at source: %s with id %s" % (row[-1], ','.join(map(str, row[0:-1]))))
                else:
                    continue
            rows[row[-1]] = { 'id_source': ','.join(map(str, row[0:-1])) }

        # get codes from odoo
        rows_odoo = self.env[self.odoo_match_id.model_id.model].search([])
        for row in rows_odoo:
            #if not rows.has_key(getattr(row, self.odoo_match_id.name)):
            #    if self.test:
            #        raise Exception("Code repeated at odoo: %s" % getattr(row, self.odoo_match_id.name))
            #    else:
            #        print 'continue'
            #        continue
            rows[getattr(row, self.odoo_match_id.name)]['id_odoo'] = str(row.id)

        codes = dict([i.code, i] for i in self.code_ids)

        for k, v in rows.items():
            if not codes.has_key(k):
                data = {
                    'translate_id': self.id,
                    'code': k,
                    'id_source': v['id_source'],
                    'id_odoo': v['id_odoo']
                }
                codes['k'] = self.env['etileno.table.translate.code'].create(data)


    source = fields.Many2one(related='table_id.source_id')
    action_ids = fields.One2many('etileno.task.action', 'translate_id')
    code_ids = fields.One2many('etileno.table.translate.code', 'translate_id')
    table_id = fields.Many2one('etileno.table')
    field_match_id = fields.Many2one('etileno.field')
    fields_complex = fields.Char()
    odoo_model = fields.Many2one(related='odoo_match_id.model_id', readonly=True)
    odoo_match_id = fields.Many2one('ir.model.fields') # default model for actions
    translate_type = fields.Selection([
        ('b', 'Basic (pks)')
    ], default='b')
    test = fields.Boolean()


class etileno_table_translate_code(models.Model):
    _name = 'etileno.table.translate.code'

    translate_id = fields.Many2one('etileno.table.translate')
    action_id = fields.Many2one('etileno.task.action')
    id_source = fields.Char() # value fields separated by commas (if there are more pk)
    code = fields.Char()
    id_odoo = fields.Char() # integer (internal id)


class etileno_row(models.TransientModel):
    """Fake model to show data from sources"""
    _name = 'etileno.row'

    table_id = fields.Many2one('etileno.table')
    a = fields.Char() # 1
    b = fields.Char() # 2
    c = fields.Char() # 3
    d = fields.Char() # 4
    e = fields.Char() # 5
    f = fields.Char() # 6
    g = fields.Char() # 7
    h = fields.Char() # 8
    i = fields.Char() # 9
    j = fields.Char() # 10


class etileno_log(models.Model):
    _name = 'etileno.log'

    name = fields.Char()
    level = fields.Selection([
        ('info', 'Info'),
        ('warning', 'Warning'),
        ('error', 'Error'),
        ('debug', 'Debug')
    ], default='info')
    time = fields.Datetime()
    message = fields.Text()
