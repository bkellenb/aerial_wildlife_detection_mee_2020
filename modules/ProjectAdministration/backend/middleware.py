'''
    Middleware layer between the project configuration front-end
    and the database.

    2019-20 Benjamin Kellenberger
'''

import os
import re
import ast
import secrets
import json
import uuid
from psycopg2 import sql
from modules.Database.app import Database
from modules.DataAdministration.backend import celery_interface as fileServer_interface
from .db_fields import Fields_annotation, Fields_prediction
from util.helpers import parse_parameters, check_args


class ProjectConfigMiddleware:

    # prohibited project shortnames
    PROHIBITED_SHORTNAMES = [
        'con',  # for MS Windows
        'prn',
        'aux',
        'nul',
        'com1',
        'com2',
        'com3',
        'com4',
        'com5',
        'com6',
        'com7',
        'com8',
        'com9',
        'lpt1',
        'lpt2',
        'lpt3',
        'lpt4',
        'lpt5',
        'lpt6',
        'lpt7',
        'lpt8',
        'lpt9'
    ]

    # prohibited project names (both as a whole and for shortnames)
    PROHIBITED_NAMES = [
        '',
        'project',
        'getavailableaimodels',
        'getbackdrops',
        'verifyprojectname',
        'verifyprojectshort',
        'newproject',
        'createproject',
        'statistics',
        'static',
        'getcreateaccountunrestricted'
        'getprojects',
        'about',
        'favicon.ico',
        'logincheck',
        'logout',
        'login',
        'dologin',
        'createaccount',
        'loginscreen',
        'accountexists',
        'getauthentication',
        'getusernames',
        'docreateaccount',
        'admin',
        'getservicedetails',
        'getceleryworkerdetails',
        'getprojectdetails',
        'getuserdetails',
        'setpassword'
    ]

    # prohibited name prefixes
    PROHIBITED_NAME_PREFIXES = [
        '/',
        '?',
        '&'
    ]

    # patterns that are prohibited anywhere for shortnames (replaced with underscores)
    SHORTNAME_PATTERNS_REPLACE = [
        '|',
        '?',
        '*',
        ':'    # for macOS
    ]

    # patterns that are prohibited anywhere for both short and long names (no replacement)
    PROHIBITED_STRICT = [
        '&lt;',
        '<',
        '>',
        '&gt;',
        '..',
        '/',
        '\\'
    ]

    
    def __init__(self, config):
        self.config = config
        self.dbConnector = Database(config)

        # load default UI settings
        try:
            # check if custom default styles are provided
            self.defaultUIsettings = json.load(open('config/default_ui_settings.json', 'r'))
        except:
            # resort to built-in styles
            self.defaultUIsettings = json.load(open('modules/ProjectAdministration/static/json/default_ui_settings.json', 'r'))


    @staticmethod
    def _recursive_update(dictObject, target):
        '''
            Recursively iterates over all keys and sub-keys of "dictObject"
            and its sub-dicts and copies over values from dict "target", if
            they are available.
        '''
        for key in dictObject.keys():
            if key in target:
                if isinstance(dictObject[key], dict):
                    ProjectConfigMiddleware._recursive_update(dictObject[key], target[key])
                else:
                    dictObject[key] = target[key]
    
    
    def getPlatformInfo(self, project, parameters=None):
        '''
            AIDE setup-specific platform metadata.
        '''
        # parse parameters (if provided) and compare with mutable entries
        allParams = set([
            'server_uri',
            'server_dir',
            'watch_folder_interval'
        ])
        if parameters is not None and parameters != '*':
            if isinstance(parameters, str):
                parameters = [parameters.lower()]
            else:
                parameters = [p.lower() for p in parameters]
            set(parameters).intersection_update(allParams)
        else:
            parameters = allParams
        parameters = list(parameters)
        response = {}
        for param in parameters:
            if param.lower() == 'server_uri':
                uri = os.path.join(self.config.getProperty('Server', 'dataServer_uri'), project, 'files')
                response[param] = uri
            elif param.lower() == 'server_dir':
                sdir = os.path.join(self.config.getProperty('FileServer', 'staticfiles_dir'), project)
                response[param] = sdir
            elif param.lower() == 'watch_folder_interval':
                interval = self.config.getProperty('FileServer', 'watch_folder_interval', type=float, fallback=60)
                response[param] = interval
        
        return response

    
    def getProjectImmutables(self, project):
        queryStr = 'SELECT annotationType, predictionType, demoMode FROM aide_admin.project WHERE shortname = %s;'
        result = self.dbConnector.execute(queryStr, (project,), 1)
        if result and len(result):
            return {
                'annotationType': result[0]['annotationtype'],
                'predictionType': result[0]['predictiontype']
            }
        else:
            return None


    def getProjectInfo(self, project, parameters=None):

        # parse parameters (if provided) and compare with mutable entries
        allParams = set([
            'name',
            'description',
            'ispublic',
            'secret_token',
            'demomode',
            'interface_enabled',
            'ui_settings',
            'segmentation_ignore_unlabeled',
            'ai_model_enabled',
            'ai_model_library',
            'ai_model_settings',
            'ai_alcriterion_library',
            'ai_alcriterion_settings',
            'numimages_autotrain',
            'minnumannoperimage',
            'maxnumimages_train',
            'watch_folder_enabled',
            'watch_folder_remove_missing_enabled'
        ])
        if parameters is not None and parameters != '*':
            if isinstance(parameters, str):
                parameters = [parameters.lower()]
            else:
                parameters = [p.lower() for p in parameters]
            set(parameters).intersection_update(allParams)
        else:
            parameters = allParams
        parameters = list(parameters)
        sqlParameters = ','.join(parameters)

        queryStr = sql.SQL('''
        SELECT {} FROM aide_admin.project
        WHERE shortname = %s;
        ''').format(
            sql.SQL(sqlParameters)
        )
        result = self.dbConnector.execute(queryStr, (project,), 1)
        result = result[0]

        # assemble response
        response = {}
        for param in parameters:
            value = result[param]
            if param == 'ui_settings':
                value = json.loads(value)

                # auto-complete with defaults where missing
                value = check_args(value, self.defaultUIsettings)
            response[param] = value

        return response


    def renewSecretToken(self, project):
        '''
            Creates a new secret token, invalidating the old one.
        '''
        try:
            newToken = secrets.token_urlsafe(32)
            result = self.dbConnector.execute('''UPDATE aide_admin.project
                SET secret_token = %s
                WHERE shortname = %s;
                SELECT secret_token FROM aide_admin.project
                WHERE shortname = %s;
            ''', (newToken, project, project,), 1)
            return result[0]['secret_token']
        except:
            # this normally should not happen, since we checked for the validity of the project
            return None


    def getProjectUsers(self, project):
        '''
            Returns a list of users that are enrolled in the project,
            as well as their roles within the project.
        '''

        queryStr = sql.SQL('SELECT * FROM aide_admin.authentication WHERE project = %s;')
        result = self.dbConnector.execute(queryStr, (project,), 'all')
        return result


    def createProject(self, username, properties):
        '''
            Receives the most basic, mostly non-changeable settings for a new project
            ("properties") with the following entries:
            - shortname
            - owner (the current username)
            - name
            - description
            - annotationType
            - predictionType

            More advanced settings (UI config, AI model, etc.) will be configured after
            the initial project creation stage.

            Verifies whether these settings are available for a new project. If they are,
            it creates a new database schema for the project, adds an entry for it to the
            admin schema table and makes the current user admin. Returns True in this case.
            Otherwise raises an exception.
        '''

        shortname = properties['shortname']

        # verify availability of the project name and shortname
        if not self.getProjectNameAvailable(properties['name']):
            raise Exception('Project name "{}" unavailable.'.format(properties['name']))
        if not self.getProjectShortNameAvailable(shortname):
            raise Exception('Project shortname "{}" unavailable.'.format(shortname))

        # load base SQL
        with open('modules/ProjectAdministration/static/sql/create_schema.sql', 'r') as f:
            queryStr = sql.SQL(f.read())

        
        # determine annotation and prediction types and add fields accordingly
        annotationFields = list(getattr(Fields_annotation, properties['annotationType']).value)
        predictionFields = list(getattr(Fields_prediction, properties['predictionType']).value)


        # create project schema
        self.dbConnector.execute(queryStr.format(
                id_schema=sql.Identifier(shortname),
                id_auth=sql.Identifier(self.config.getProperty('Database', 'user')),
                id_image=sql.Identifier(shortname, 'image'),
                id_iu=sql.Identifier(shortname, 'image_user'),
                id_labelclassGroup=sql.Identifier(shortname, 'labelclassgroup'),
                id_labelclass=sql.Identifier(shortname, 'labelclass'),
                id_annotation=sql.Identifier(shortname, 'annotation'),
                id_cnnstate=sql.Identifier(shortname, 'cnnstate'),
                id_prediction=sql.Identifier(shortname, 'prediction'),
                id_workflow=sql.Identifier(shortname, 'workflow'),
                id_workflowHistory=sql.Identifier(shortname, 'workflowhistory'),
                annotation_fields=sql.SQL(', ').join([sql.SQL(field) for field in annotationFields]),
                prediction_fields=sql.SQL(', ').join([sql.SQL(field) for field in predictionFields])
            ),
            None,
            None
        )

        # register project
        self.dbConnector.execute('''
            INSERT INTO aide_admin.project (shortname, name, description,
                owner,
                secret_token,
                interface_enabled,
                annotationType, predictionType,
                isPublic, demoMode,
                ui_settings)
            VALUES (
                %s, %s, %s,
                %s,
                %s,
                %s,
                %s, %s,
                %s, %s,
                %s
            );
            ''',
            (
                shortname,
                properties['name'],
                (properties['description'] if 'description' in properties else ''),
                username,
                secrets.token_urlsafe(32),
                False,
                properties['annotationType'],
                properties['predictionType'],
                False, False,
                json.dumps(self.defaultUIsettings)
            ),
            None)

        # register user in project
        self.dbConnector.execute('''
                INSERT INTO aide_admin.authentication (username, project, isAdmin)
                VALUES (%s, %s, true);
            ''',
            (username, shortname,),
            None)

        # notify FileServer instance(s) to set up project folders
        process = fileServer_interface.aide_internal_notify.si({
            'task': 'create_project_folders',
            'projectName': shortname
        })
        process.apply_async(queue='aide_broadcast',
                            ignore_result=True)
        
        return True



    def updateProjectSettings(self, project, projectSettings):
        '''
            TODO
        '''

        # check UI settings first
        if 'ui_settings' in projectSettings:
            if isinstance(projectSettings['ui_settings'], str):
                projectSettings['ui_settings'] = json.loads(projectSettings['ui_settings'])
            fieldNames = [
                ('welcomeMessage', str),
                ('numImagesPerBatch', int),
                ('minImageWidth', int),
                ('numImageColumns_max', int),
                ('defaultImage_w', int),
                ('defaultImage_h', int),
                ('styles', dict),
                ('enableEmptyClass', bool),
                ('showPredictions', bool),
                ('showPredictions_minConf', float),
                ('carryOverPredictions', bool),
                ('carryOverRule', str),
                ('carryOverPredictions_minConf', float),
                ('defaultBoxSize_w', int),
                ('defaultBoxSize_h', int),
                ('minBoxSize_w', int),
                ('minBoxSize_h', int)
            ]
            uiSettings_new, uiSettingsKeys_new = parse_parameters(projectSettings['ui_settings'], fieldNames, absent_ok=True, escape=True)   #TODO: escape
            
            # adopt current settings and replace values accordingly
            uiSettings = self.dbConnector.execute('''SELECT ui_settings
                    FROM aide_admin.project
                    WHERE shortname = %s;            
                ''', (project,), 1)
            uiSettings = json.loads(uiSettings[0]['ui_settings'])
            for kIdx in range(len(uiSettingsKeys_new)):
                if isinstance(uiSettings[uiSettingsKeys_new[kIdx]], dict):
                    ProjectConfigMiddleware._recursive_update(uiSettings[uiSettingsKeys_new[kIdx]], uiSettings_new[kIdx])
                else:
                    uiSettings[uiSettingsKeys_new[kIdx]] = uiSettings_new[kIdx]

            # auto-complete with defaults where missing
            uiSettings = check_args(uiSettings, self.defaultUIsettings)

            projectSettings['ui_settings'] = json.dumps(uiSettings)


        # parse remaining parameters
        fieldNames = [
            ('description', str),
            ('isPublic', bool),
            ('secret_token', str),
            ('demoMode', bool),
            ('ui_settings', str),
            ('interface_enabled', bool),
            ('watch_folder_enabled', bool),
            ('watch_folder_remove_missing_enabled', bool)
        ]

        vals, params = parse_parameters(projectSettings, fieldNames, absent_ok=True, escape=False)
        vals.append(project)

        # commit to DB
        queryStr = sql.SQL('''UPDATE aide_admin.project
            SET
            {}
            WHERE shortname = %s;
            '''
        ).format(
            sql.SQL(',').join([sql.SQL('{} = %s'.format(item)) for item in params])
        )

        self.dbConnector.execute(queryStr, tuple(vals), None)

        return True

    

    def updateClassDefinitions(self, project, classdef, removeMissing=False):
        '''
            Updates the project's class definitions.
            if "removeMissing" is set to True, label classes that are present
            in the database, but not in "classdef," will be removed. Label
            class groups will only be removed if they do not reference any
            label class present in "classdef." This functionality is disallowed
            in the case of segmentation masks.
        '''

        # check if project contains segmentation masks
        metaType = self.dbConnector.execute('''
                SELECT annotationType, predictionType FROM aide_admin.project
                WHERE shortname = %s;
            ''',
            (project,),
            1
        )[0]
        is_segmentation = any(['segmentationmasks' in m.lower() for m in metaType.values()])
        if is_segmentation:
            removeMissing = False

        # get current classes from database
        db_classes = {}
        db_groups = {}
        if removeMissing:
            queryStr = sql.SQL('''
                SELECT * FROM {id_lc} AS lc
                FULL OUTER JOIN (
                    SELECT id AS lcgid, name AS lcgname, parent, color
                    FROM {id_lcg}
                ) AS lcg
                ON lc.labelclassgroup = lcg.lcgid
            ''').format(
                id_lc=sql.Identifier(project, 'labelclass'),
                id_lcg=sql.Identifier(project, 'labelclassgroup')
            )
            result = self.dbConnector.execute(queryStr, None, 'all')
            for r in result:
                if r['id'] is not None:
                    db_classes[r['id']] = r
                if r['lcgid'] is not None:
                    if not r['lcgid'] in db_groups:
                        db_groups[r['lcgid']] = {**r, **{'num_children':0}}
                    elif not 'lcgid' in db_groups[r['lcgid']]:
                        db_groups[r['lcgid']] = {**db_groups[r['lcgid']], **r}
                if r['labelclassgroup'] is not None:
                    if not r['labelclassgroup'] in db_groups:
                        db_groups[r['labelclassgroup']] = {'num_children':1}
                    else:
                        db_groups[r['labelclassgroup']]['num_children'] += 1

        # parse provided class definitions list
        unique_keystrokes = set()
        classes_update = []
        classgroups_update = []
        def _parse_item(item, parent=None):
            # get or create ID for item
            try:
                itemID = uuid.UUID(item['id'])
            except:
                itemID = uuid.uuid1()
                while itemID in classes_update or itemID in classgroups_update:
                    itemID = uuid.uuid1()

            entry = {
                'id': itemID,
                'name': item['name'],
                'color': (None if not 'color' in item else item['color']),
                'keystroke': None,
                'labelclassgroup': parent
            }
            if 'children' in item:
                # label class group
                classgroups_update.append(entry)
                for child in item['children']:
                    _parse_item(child, itemID)
            else:
                # label class
                if 'keystroke' in item and not item['keystroke'] in unique_keystrokes:
                    entry['keystroke'] = item['keystroke']
                    unique_keystrokes.add(item['keystroke'])
                classes_update.append(entry)

        for item in classdef:
            _parse_item(item, None)
        
        # apply changes
        if removeMissing:
            queryArgs = []
            if len(classes_update):
                # remove all missing label classes
                lcSpec = sql.SQL('WHERE id NOT IN %s')
                queryArgs.append(tuple([(l['id'],) for l in classes_update]))
            else:
                # remove all label classes
                lcgSpec = sql.SQL('')
            if len(classgroups_update):
                # remove all missing labelclass groups
                lcgSpec = sql.SQL('WHERE id NOT IN %s')
                queryArgs.append(tuple([(l['id'],) for l in classgroups_update]))
            else:
                # remove all labelclass groups
                lcgSpec = sql.SQL('')
            queryStr = sql.SQL('''
                DELETE FROM {id_lc}
                {lcSpec};
                DELETE FROM {id_lcg}
                {lcgSpec};
            ''').format(
                id_lc=sql.Identifier(project, 'labelclass'),
                id_lcg=sql.Identifier(project, 'labelclassgroup'),
                lcSpec=lcSpec,
                lcgSpec=lcgSpec
            )
            self.dbConnector.execute(queryStr, tuple(queryArgs), None)
        
        # add/update in order (groups, set their parents, label classes)
        groups_new = [(g['id'], g['name'], g['color'],) for g in classgroups_update]
        queryStr = sql.SQL('''
            INSERT INTO {id_lcg} (id, name, color)
            VALUES %s
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                color = EXCLUDED.color;
        ''').format(        #TODO: on conflict(name)
            id_lcg=sql.Identifier(project, 'labelclassgroup')
        )
        self.dbConnector.insert(queryStr, groups_new)

        # set parents
        groups_parents = [(g['id'], g['labelclassgroup'],) for g in classgroups_update if ('labelclassgroup' in g and g['labelclassgroup'] is not None)]
        queryStr = sql.SQL('''
            UPDATE {id_lcg} AS lcg
            SET parent = q.parent
            FROM (VALUES %s) AS q(id, parent)
            WHERE lcg.id = q.id;
        ''').format(
            id_lcg=sql.Identifier(project, 'labelclassgroup')
        )
        self.dbConnector.insert(queryStr, groups_parents)

        # insert/update label classes
        lcdata = [(l['id'], l['name'], l['color'], l['keystroke'], l['labelclassgroup'],) for l in classes_update]
        queryStr = sql.SQL('''
            INSERT INTO {id_lc} (id, name, color, keystroke, labelclassgroup)
            VALUES %s
            ON CONFLICT (id) DO UPDATE
            SET name = EXCLUDED.name,
            color = EXCLUDED.color,
            keystroke = EXCLUDED.keystroke,
            labelclassgroup = EXCLUDED.labelclassgroup;
        ''').format(    #TODO: on conflict(name)
            id_lc=sql.Identifier(project, 'labelclass')
        )
        self.dbConnector.insert(queryStr, lcdata)

        return True



    def getProjectNameAvailable(self, projectName):
        '''
            Returns True if the provided project (long) name is available.
        '''
        if not isinstance(projectName, str):
            return False
        projectName = projectName.strip().lower()
        if not len(projectName):
            return False

        # check if name matches prohibited AIDE keywords (we do not replace long names)
        if projectName in self.PROHIBITED_STRICT or any([p in projectName for p in self.PROHIBITED_STRICT]):
            return False
        if projectName in self.PROHIBITED_NAMES:
            return False
        if any([projectName.startswith(p) for p in self.PROHIBITED_NAME_PREFIXES]):
            return False

        # check if name is already taken
        result = self.dbConnector.execute('''SELECT 1 AS result
            FROM aide_admin.project
            WHERE name = %s;
            ''',
            (projectName,),
            1)
        
        if result is None or not len(result):
            return True
        else:
            return result[0]['result'] != 1


    def getProjectShortNameAvailable(self, projectName):
        '''
            Returns True if the provided project shortname is available.
            In essence, "available" means that a database schema with the given
            name can be created (this includes Postgres schema name conventions).
            Returns False otherwise.
        '''
        if not isinstance(projectName, str):
            return False
        projectName = projectName.strip().lower()
        if not len(projectName):
            return False

        # check if name matches prohibited AIDE keywords; replace where possible
        if projectName in self.PROHIBITED_STRICT or any([p in projectName for p in self.PROHIBITED_STRICT]):
            return False
        if projectName in self.PROHIBITED_NAMES or projectName in self.PROHIBITED_SHORTNAMES:
            return False
        if any([projectName.startswith(p) for p in self.PROHIBITED_NAME_PREFIXES]):
            return False
        for p in self.SHORTNAME_PATTERNS_REPLACE:
            projectName = projectName.replace(p, '_')

        # check if provided name is valid as per Postgres conventions
        matches = re.findall('(^(pg_|[0-9]).*|.*(\$|\s)+.*)', projectName)
        if len(matches):
            return False

        # check if project shorthand already exists in database
        result = self.dbConnector.execute('''SELECT 1 AS result
            FROM information_schema.schemata
            WHERE schema_name ilike %s
            UNION ALL
            SELECT 1 FROM aide_admin.project
            WHERE shortname ilike %s;
            ''',
            (projectName,projectName,),
            2)

        if result is None or not len(result):
            return True

        if len(result) == 2:
            return result[0]['result'] != 1 and result[1]['result'] != 1
        elif len(result) == 1:
            return result[0]['result'] != 1
        else:
            return True