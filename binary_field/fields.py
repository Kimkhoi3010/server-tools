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
from openerp import tools
import os
import sys
import logging

_logger = logging.getLogger(__name__)


class Storage(object):

    def __init__(self, cr, uid, record, field_name, config=None):
        self.cr = cr
        self.uid = uid
        self.pool = record._model.pool
        if config and config.get('field_key'):
            self.field_key = config['field_key']
        else:
            self.field_key = (
                "%s-%s" % (record._name, field_name)).replace('.', '')
        if config and config.get('base_location'):
            self.base_location = config['base_location']
        else:
            self.base_location = self.pool.get('ir.config_parameter').\
                get_param(cr, uid, 'binary.location')
            if not self.base_location:
                raise orm.except_orm(
                    _('Configuration Error'),
                    _('The "binary.location" is empty, please fill it in'
                      'Configuration > Parameters > System Parameters'))
        self.location = (self.base_location, self.field_key)

    def add(self, value):
        if not value:
            return {}
        file_size = sys.getsizeof(value.decode('base64'))
        binary_uid = self.pool['ir.attachment'].\
            _file_write(self.cr, self.uid, self.location, value)
        _logger.debug('Add binary %s/%s' % (self.field_key, binary_uid))
        return {
            'binary_uid': binary_uid,
            'file_size': file_size,
            }

    def update(self, binary_uid, value):
        _logger.debug('Delete binary %s/%s' % (self.field_key, binary_uid))
        self.pool['ir.attachment'].\
            _file_delete(self.cr, self.uid, self.location, binary_uid)
        if not value:
            return {}
        return self.add(value)

    def get(self, binary_uid):
        return self.pool['ir.attachment'].\
            _file_read(self.cr, self.uid, self.location, binary_uid)


class BinaryField(fields.function):

    def __init__(self, string, get_storage=Storage, config=None, **kwargs):
        """Init a BinaryField field
        :params string: Name of the field
        :type string: str
        :params get_storage: Storage Class for processing the field
                            by default use the Storage on filesystem
        :type get_storage: :py:class`binary_field.Storage'
        :params config: configuration used by the storage class
        :type config: what you want it's depend of the Storage class
                      implementation
        """
        new_kwargs = {
            'type': 'binary',
            'string': string,
            'fnct_inv': self._fnct_write,
            'multi': False,
            }
        new_kwargs.update(kwargs)
        self.get_storage = get_storage
        self.config = config
        super(BinaryField, self).__init__(self._fnct_read, **new_kwargs)

    # No postprocess are needed
    # we already take care of bin_size option in the context
    def postprocess(self, cr, uid, obj, field, value=None, context=None):
        return value

    def _prepare_binary_meta(self, cr, uid, field_name, res, context=None):
        return {
            '%s_uid' % field_name: res.get('binary_uid'),
            '%s_file_size' % field_name: res.get('file_size'),
            }

    def _fnct_write(self, obj, cr, uid, ids, field_name, value, args,
                    context=None):
        if not isinstance(ids, (list, tuple)):
            ids = [ids]
        for record in obj.browse(cr, uid, ids, context=context):
            storage = self.get_storage(cr, uid, record, field_name,
                                       config=self.config)
            binary_uid = record['%s_uid' % field_name]
            if binary_uid:
                res = storage.update(binary_uid, value)
            else:
                res = storage.add(value)
            vals = self._prepare_binary_meta(
                cr, uid, field_name, res, context=context)
            record.write(vals)
        return True

    def _fnct_read(self, obj, cr, uid, ids, field_name, args, context=None):
        result = {}
        for record in obj.browse(cr, uid, ids, context=context):
            storage = self.get_storage(cr, uid, record, field_name,
                                       config=self.config)
            binary_uid = record['%s_uid' % field_name]
            if binary_uid:
                # Compatibility with existing binary field
                if context.get(
                    'bin_size_%s' % field_name, context.get('bin_size')
                ):
                    size = record['%s_file_size' % field_name]
                    result[record.id] = tools.human_size(long(size))
                else:
                    result[record.id] = storage.get(binary_uid)
            else:
                result[record.id] = None
        return result


class ImageField(BinaryField):

    def __init__(self, string, get_storage=Storage, config=None, 
            resize_based_on=None, height=64, width=64, **kwargs):
        """Init a ImageField field
        :params string: Name of the field
        :type string: str
        :params get_storage: Storage Class for processing the field
                            by default use the Storage on filesystem
        :type get_storage: :py:class`binary_field.Storage'
        :params config: configuration used by the storage class
        :type config: what you want it's depend of the Storage class
                      implementation
        :params resize_based_on: reference field that should be resized
        :type resize_based_on: str
        :params height: height of the image resized
        :type height: integer
        :params width: width of the image resized
        :type width: integer
        """
        super(ImageField, self).__init__(
            string,
            get_storage=get_storage,
            config=config,
            **kwargs)
        self.resize_based_on = resize_based_on
        self.height = height
        self.width = width

    def _fnct_write(self, obj, cr, uid, ids, field_name, value, args,
                    context=None):
        if context is None:
            context = {}
        related_field_name = obj._columns[field_name].resize_based_on

        # If we write an original image in a field with the option resized
        # We have to store the image on the related field and not on the
        # resized image field
        if related_field_name and not context.get('refresh_image_cache'):
            return self._fnct_write(
                obj, cr, uid, ids, related_field_name, value, args,
                context=context)
        else:
            super(ImageField, self)._fnct_write(
                obj, cr, uid, ids, field_name, value, args, context=context)
            
            for name, field in obj._columns.items():
                if isinstance(field, ImageField)\
                   and field.resize_based_on == field_name:
                    field._refresh_cache(
                        obj, cr, uid, ids, name, context=context)
        return True

    def _refresh_cache(self, obj, cr, uid, ids, field_name, context=None):
        """Refresh the cache of the small image
        :params ids: list of object id to refresh
        :type ids: list
        :params field_name: Name of the field to refresh the cache
        :type field_name: str
        """
        if context is None:
            context = {}
        if not isinstance(ids, (list, tuple)):
            ids = [ids]
        for record_id in ids:
            _logger.debug('Refreshing Image Cache from the field %s of object '
                          '%s id : %s' % (field_name, obj._name, record_id))
            field = obj._columns[field_name]
            record = obj.browse(cr, uid, record_id, context=context)
            original_image = record[field.resize_based_on]
            if original_image:
                size = (field.height, field.width)
                resized_image = image_resize_image(original_image, size)
            else:
                resized_image = None
            ctx = context.copy()
            ctx['refresh_image_cache'] = True
            self._fnct_write(obj, cr, uid, [record_id], field_name,
                             resized_image, None, context=ctx)


fields.BinaryField = BinaryField
fields.ImageField = ImageField


original__init__ = orm.BaseModel.__init__


def __init__(self, pool, cr):
    original__init__(self, pool, cr)
    if self.pool.get('binary.field.installed'):
        additional_field = {}
        for field_name in self._columns:
            field = self._columns[field_name]
            if isinstance(field, BinaryField):
                additional_field.update({
                    '%s_uid' % field_name:
                        fields.char('%s UID' % self._columns[field_name].string),
                    '%s_file_size' % field_name:
                        fields.integer(
                            '%s File Size' % self._columns[field_name].string),
                    })
                #import pdb; pdb.set_trace()
        self._columns.update(additional_field)


orm.BaseModel.__init__ = __init__


class IrAttachment(orm.Model):
    _inherit = 'ir.attachment'

    def _full_path(self, cr, uid, location, path):
        # Hack for passing the field_key in the full path
        # For now I prefer to use this hack and to reuse
        # the ir.attachment code
        # An alternative way will to copy/paste and
        # adapt the ir.attachment code
        if isinstance(location, tuple):
            base_location, field_key = location
            path = os.path.join(field_key, path)
        else:
            base_location = location
        return super(IrAttachment, self).\
            _full_path(cr, uid, base_location, path)


class BinaryFieldInstalled(orm.AbstractModel):
    _name = 'binary.field.installed'
