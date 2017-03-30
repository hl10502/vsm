
# Copyright 2014 Intel Corporation, All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the"License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#  http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.

from django.core.urlresolvers import reverse
try:
    from django.utils.translation import force_unicode
except:
    from django.utils.translation import force_text as force_unicode

from django.utils.translation import  ugettext_lazy as _

from horizon import exceptions
from horizon import forms
from horizon import messages
from horizon.utils.validators import validate_port_range
from horizon.utils import validators
# from horizon.utils import fields
import logging
from django.forms import ValidationError
from django import http
from django.conf import settings
from django import shortcuts

from vsm_dashboard.api import vsm as vsm_api
from vsm_dashboard import api
from vsm_dashboard.utils.validators import validate_user_name
from vsm_dashboard.utils.validators import password_validate_regrex

LOG = logging.getLogger(__name__)

class BaseServerForm(forms.SelfHandlingForm):
    def __init__(self, request, *args, **kwargs):
        super(BaseServerForm, self).__init__(request, *args, **kwargs)
        # Populate tenant choices

    def clean(self):
        '''Check to make sure password fields match.'''
        data = super(forms.Form, self).clean()
        if 'password' in data:

            if data['password'] != data.get('confirm_password', None):
                raise ValidationError(_('Passwords do not match.'))
        return data

class InstallServersForm(BaseServerForm):
    failure_url = 'horizon:vsm:storageservermgmt:index'
    serverIp = forms.CharField(label=_("Server IP"),
           max_length=255,
           min_length=1,
           error_messages={
           'required': _('This field is required.'),
           'invalid': _("Please enter a vaild Server IP")},
           validators= [validate_user_name,]
           )
    sshUserName = forms.CharField(label=_("SSH UserName"),
            max_length=255,
            min_length=8,
            error_messages={'invalid':
                    validators.password_validator_msg()})

    def handle(self, request, data):
        pass

