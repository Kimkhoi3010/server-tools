# -*- coding: utf-8 -*-
###############################################################################
#
#   Module for OpenERP
#   Copyright (C) 2014 Akretion (http://www.akretion.com).
#   @author Sébastien BEAU <sebastien.beau@akretion.com>
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################

from openerp.osv import fields, orm
from openerp.tools import image_resize_image
from openerp.tools.translate import _
import os
import logging

_logger = logging.getLogger(__name__)


class BinaryBinary(orm.Model):
    _name = 'binary.binary'
    _description = 'binary.binary'

    _columns = {
        #'name': fields.char('Name',size=256, required=True),
        'store_fname': fields.char('Stored Filename', size=256),
        #'extension': fields.char('Extension', size=4),
        'file_size': fields.integer('File Size'),
    }

    def _get_location(self, cr, uid):
        base_location = self.pool.get('ir.config_parameter').\
            get_param(cr, uid, 'binary.location')
        if not base_location:
            raise orm.except_orm(
                _('Configuration Error'),
                _('The "binary.location" is empty, please fill it in'
                  'Configuration > Parameters > System Parameters'))
        return base_location

    def add(self, cr, uid, value, field_key, context=None):
        if not value:
            return None
        base_location = self._get_location(cr, uid)
        # Hack for passing the field_key in the full path
        location = (base_location, field_key)
        file_size = len(value.decode('base64'))
        fname = self._file_write(cr, uid, location, value)
        return self.create(cr, uid, {
            'store_fname': fname,
            'file_size': file_size,
            }, context=context)

    def update(self, cr, uid, binary_id, value, field_key, context=None):
        binary = self.browse(cr, uid, binary_id, context=context)
        base_location = self._get_location(cr, uid)
        # Hack for passing the field_key in the full path
        location = (base_location, field_key)
        self._file_delete(cr, uid, location, binary.store_fname)
        if not value:
            return None
        fname = self._file_write(cr, uid, location, value)
        file_size = len(value.decode('base64'))
        self.write(cr, uid, binary_id, {
            'store_fname': fname,
            'file_size': file_size,
            }, context=context)
        return True

    def get_content(self, cr, uid, field_key, binary_id, context=None):
        binary = self.browse(cr, uid, binary_id, context=context)
        base_location = self._get_location(cr, uid)
        # Hack for passing the field_key in the full path
        location = (base_location, field_key)
        return self._file_read(cr, uid, location, binary.store_fname)

    def _file_read(self, cr, uid, location, fname):
        return self.pool['ir.attachment']._file_read(cr, uid, location, fname)

    def _file_write(self, cr, uid, location, value):
        return self.pool['ir.attachment']._file_write(cr, uid, location, value)

    def _file_delete(self, cr, uid, location, fname):
        return self.pool['ir.attachment']._file_delete(cr, uid, location, fname)


class IrAttachment(orm.Model):
    _inherit = 'ir.attachment'

    def _full_path(self, cr, uid, location, path):
        #TODO add the posibility to customise the field_key
        #maybe we can add a the field key in the ir.config.parameter
        #and then retrieve an new path base on the config?

        # Hack for passing the field_key in the full path
        if isinstance(location, tuple):
            base_location, field_key = location
            path = os.path.join(field_key, path)
        else:
            base_location = location
        return super(IrAttachment, self).\
            _full_path(cr, uid, base_location, path)


class BinaryField(fields.function):

    def __init__(self, string, filters=None, **kwargs):
        new_kwargs = {
            'type': 'binary',
            'string': string,
            'fnct': self._fnct_read,
            'fnct_inv': self._fnct_write,
            'multi': False,
            }
        new_kwargs.update(kwargs)
        self.filters = filters
        super(BinaryField, self).__init__(**new_kwargs)

    def _get_binary_id(self, cr, uid, obj, field_name, record_id, context=None):
        cr.execute(
            "SELECT " + field_name + "_info_id FROM "
            + obj._table + " WHERE id = %s",
            (record_id,))
        return cr.fetchone()[0]
    
    def _build_field_key(self, obj, field_name):
        return "%s-%s" % (obj._name, field_name)

    def _get_binary(self, cr, uid, obj, field_name, record_id, context=None):
        binary_obj = obj.pool['binary.binary']
        binary_id = self._get_binary_id(
            cr, uid, obj, field_name, record_id, context=context)
        if not binary_id:
            return None
        field_key = self._build_field_key(obj, field_name)
        return binary_obj.get_content(
            cr, uid, field_key, binary_id, context=context)

    def _fnct_write(self, obj, cr, uid, ids, field_name, value, args,
                    context=None):
        if not isinstance(ids, (list, tuple)):
            ids = [ids]
        binary_obj = obj.pool['binary.binary']
        for record_id in ids:
            field_key = self._build_field_key(obj, field_name)
            binary_id = self._get_binary_id(
                cr, uid, obj, field_name, record_id, context=context)
            if binary_id:
                res_id = binary_obj.update(
                    cr, uid, binary_id, value, field_key, context=context)
            else:
                res_id = binary_obj.add(
                    cr, uid, value, field_key, context=context)
                obj.write(cr, uid, record_id, {
                    '%s_info_id' % field_name: res_id,
                    }, context=context)
        return True

    def _fnct_read(self, obj, cr, uid, ids, field_name, args, context=None):
        result = {}
        for record_id in ids:
            result[record_id] = self._get_binary(
                cr, uid, obj, field_name, record_id, context=context)

#TODO do not forget to add this for compatibility with binary field
#            if val and context.get('bin_size_%s' % name, context.get('bin_size')):
#                res[i] = tools.human_size(long(val))
#            else:
#                res[i] = val
        return result


class ImageField(BinaryField):

    def __init__(self, string, filters=None, **kwargs):
        self.filters = filters
        super(ImageField, self).__init__(
            string=string,
            **kwargs)

    def _fnct_write(self, obj, cr, uid, ids, field_name, value, args,
                    context=None):
        super(ImageField, self)._fnct_write(
            obj, cr, uid, ids, field_name, value, args, context=context)
        for name, field in obj._columns.items():
            if isinstance(field, ImageResizeField) \
                    and field.related_field == field_name:
                field._refresh_cache(
                    obj, cr, uid, ids, name, context=context)
        return True


class ImageResizeField(ImageField):

    def __init__(self, string, related_field, height, width,
                 filters=None, **kwargs):
        self.filters = filters
        self.height = height
        self.width = width
        self.related_field = related_field
        super(ImageResizeField, self).__init__(
            string=string,
            **kwargs)

    def _get_binary(self, cr, uid, obj, field_name, record_id, context=None):
        #Idée via le fonction store, je trigger le write
        #et la en fonciton du mode soit simplement je vire les images
        #soit je les vire et je les regénère
        if context.get('bin_size'):
            return 2
        return super(ImageResizeField, self)._get_binary(
            cr, uid, obj, field_name, record_id, context=context)

    def _refresh_cache(self, obj, cr, uid, ids, field_name, context=None):
        if not isinstance(ids, (list, tuple)):
            ids = [ids]
        for record_id in ids:
            _logger.debug('Refresh Image Cache from the field %s of object %s '
                          'id : %s' % (field_name, obj._name, record_id))
            field = obj._columns[field_name]
            record = obj.browse(cr, uid, record_id, context=context)
            original_image = record[field.related_field]
            if original_image:
                size = (field.height, field.width)
                resized_image = image_resize_image(original_image, size)
            else:
                resized_image = None
            ctx = context.copy()
            ctx['refresh_image_cache'] = True
            self._fnct_write(obj, cr, uid, [record_id], field_name,
                             resized_image, None, context=ctx)

    def _fnct_write(self, obj, cr, uid, ids, field_name, value, args,
                    context=None):
        if context is not None and context.get('refresh_image_cache'):
            field = field_name
        else:
            field = obj._columns[field_name].related_field
        return super(ImageResizeField, self)._fnct_write(
            obj, cr, uid, ids, field, value, args, context=context)


fields.BinaryField = BinaryField
fields.ImageField = ImageField
fields.ImageResizeField = ImageResizeField


original__init__ = orm.BaseModel.__init__


def __init__(self, pool, cr):
    original__init__(self, pool, cr)
    if self.pool.get('binary.binary'):
        additionnal_field = {}
        for field in self._columns:
            if isinstance(self._columns[field], BinaryField):
                additionnal_field['%s_uid' % field] = \
                    fields.char('%s UID' % self._columns[field].string)

            #Inject the store invalidation function for ImageResize
            if isinstance(self._columns[field], ImageResizeField):
                self._columns[field].store = {
                    self._name: (
                        lambda self, cr, uid, ids, c={}: ids,
                        [self._columns[field].related_field],
                        10),
                }
        self._columns.update(additionnal_field)


orm.BaseModel.__init__ = __init__
