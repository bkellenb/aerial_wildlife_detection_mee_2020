'''
    2019-20 Benjamin Kellenberger
'''

import inspect
import json
from psycopg2 import sql
from celery import current_app
from kombu import Queue
from modules.AIWorker.backend.worker import functional
from modules.AIWorker.backend import fileserver
from modules.Database.app import Database
from util.helpers import get_class_executable


class AIWorker():

    def __init__(self, config, passiveMode=False):
        self.config = config
        self.dbConnector = Database(config)
        self.passiveMode = passiveMode
        self._init_fileserver()
            

    def _init_fileserver(self):
        '''
            The AIWorker has a special routine to detect whether the instance it is running on
            also hosts the file server. If it does, data are loaded directly from disk to avoid
            going through the loopback network.
        '''
        self.fileServer = fileserver.FileServer(self.config)


    def _init_model_instance(self, project, modelLibrary, modelSettings):

        # try to parse model settings
        if modelSettings is not None and len(modelSettings):
            try:
                modelSettings = json.loads(modelSettings)
            except Exception as err:
                print('WARNING: could not read model options. Error message: {message}.'.format(
                    message=str(err)
                ))
                modelSettings = None
        else:
            modelSettings = None

        # import class object
        modelClass = get_class_executable(modelLibrary)

        # verify functions and arguments
        requiredFunctions = {
            '__init__' : ['project', 'config', 'dbConnector', 'fileServer', 'options'],
            'train' : ['stateDict', 'data', 'updateStateFun'],
            'average_model_states' : ['stateDicts', 'updateStateFun'],
            'inference' : ['stateDict', 'data', 'updateStateFun']
        }
        functionNames = [func for func in dir(modelClass) if callable(getattr(modelClass, func))]

        for key in requiredFunctions:
            if not key in functionNames:
                raise Exception('Class {} is missing required function {}.'.format(modelLibrary, key))

            # check function arguments bidirectionally
            funArgs = inspect.getargspec(getattr(modelClass, key))
            for arg in requiredFunctions[key]:
                if not arg in funArgs.args:
                    raise Exception('Method {} of class {} is missing required argument {}.'.format(modelLibrary, key, arg))
            for arg in funArgs.args:
                if arg != 'self' and not arg in requiredFunctions[key]:
                    raise Exception('Unsupported argument {} of method {} in class {}.'.format(arg, key, modelLibrary))

        # create AI model instance
        return modelClass(project=project,
                            config=self.config,
                            dbConnector=self.dbConnector,
                            fileServer=self.fileServer.get_secure_instance(project),
                            options=modelSettings)
        

    def _init_alCriterion_instance(self, project, alLibrary, alSettings):
        '''
            Creates the Active Learning (AL) criterion provider instance.
        '''
        # try to parse settings
        if alSettings is not None and len(alSettings):
            try:
                alSettings = json.loads(alSettings)
            except Exception as err:
                print('WARNING: could not read AL criterion options. Error message: {message}.'.format(
                    message=str(err)
                ))
                alSettings = None
        else:
            alSettings = None

        # import class object
        modelClass = get_class_executable(alLibrary)

        # verify functions and arguments
        requiredFunctions = {
            '__init__' : ['project', 'config', 'dbConnector', 'fileServer', 'options'],
            'rank' : ['data', 'updateStateFun']
        }
        functionNames = [func for func in dir(modelClass) if callable(getattr(modelClass, func))]

        for key in requiredFunctions:
            if not key in functionNames:
                raise Exception('Class {} is missing required function {}.'.format(alLibrary, key))

            # check function arguments bidirectionally
            funArgs = inspect.getargspec(getattr(modelClass, key))
            for arg in requiredFunctions[key]:
                if not arg in funArgs.args:
                    raise Exception('Method {} of class {} is missing required argument {}.'.format(alLibrary, key, arg))
            for arg in funArgs.args:
                if arg != 'self' and not arg in requiredFunctions[key]:
                    raise Exception('Unsupported argument {} of method {} in class {}.'.format(arg, key, alLibrary))

        # create AI model instance
        return modelClass(project=project,
                            config=self.config,
                            dbConnector=self.dbConnector,
                            fileServer=self.fileServer.get_secure_instance(project),
                            options=alSettings)


    def _get_model_instance(self, project):
        '''
            Returns the class instance of the model specified in the given
            project.
            TODO: cache models?
        '''
        # get model settings for project
        queryStr = '''
            SELECT ai_model_library, ai_model_settings FROM aide_admin.project
            WHERE shortname = %s;
        '''
        result = self.dbConnector.execute(queryStr, (project,), 1)
        modelLibrary = result[0]['ai_model_library']
        modelSettings = result[0]['ai_model_settings']

        # create new model instance
        modelInstance = self._init_model_instance(project, modelLibrary, modelSettings)

        return modelInstance


    def _get_alCriterion_instance(self, project):
        '''
            Returns the class instance of the Active Learning model
            specified in the project.
            TODO: cache models?
        '''
        # get model settings for project
        queryStr = '''
            SELECT ai_alCriterion_library, ai_alCriterion_settings FROM aide_admin.project
            WHERE shortname = %s;
        '''
        result = self.dbConnector.execute(queryStr, (project,), 1)
        modelLibrary = result[0]['ai_alcriterion_library']
        modelSettings = result[0]['ai_alcriterion_settings']

        # create new model instance
        modelInstance = self._init_alCriterion_instance(project, modelLibrary, modelSettings)

        return modelInstance



    def aide_internal_notify(self, message):
        '''
            Used for AIDE administrative communication between AIController
            and AIWorker(s), e.g. for setting up queues.
        '''
        if self.passiveMode:
            return
        # not required (yet)



    def call_train(self, data, epoch, numEpochs, project, subset):

        # get project-specific model
        modelInstance = self._get_model_instance(project)

        return functional._call_train(project, data, epoch, numEpochs, subset, getattr(modelInstance, 'train'),
                self.dbConnector, self.fileServer)
    


    def call_average_model_states(self, epoch, numEpochs, project):

        # get project-specific model
        modelInstance = self._get_model_instance(project)
        
        return functional._call_average_model_states(project, epoch, numEpochs, getattr(modelInstance, 'average_model_states'),
                self.dbConnector, self.fileServer)



    def call_inference(self, imageIDs, epoch, numEpochs, project):
        
        # get project-specific model and AL criterion
        modelInstance = self._get_model_instance(project)
        alCriterionInstance = self._get_alCriterion_instance(project)

        return functional._call_inference(project, imageIDs, epoch, numEpochs,
                getattr(modelInstance, 'inference'),
                getattr(alCriterionInstance, 'rank'),
                self.dbConnector, self.fileServer,
                self.config.getProperty('AIWorker', 'inference_batch_size_limit', type=int, fallback=-1))



    def verify_model_state(self, project, modelLibrary, stateDict, modelOptions):
        '''
            Launches a dummy training-averaging-inference chain
            on a received model state and returns True if the chain
            could be executed without any errors (else False). Does
            not store anything in the database.
            Inputs:
                - project:      str, project shortname (used to retrieve
                                sample data)
                - modelLibrary: str, identifier of the AI model
                - stateDict:    bytes object, AI model state
                - modelOptions: str, model settings to be tested
                                (optional)
            
            Returns a dict with the following entries:
                - valid:    bool, True if the provided state dict and
                            (optionally) model options are valid (i.e.,
                            can be used to perform training, averaging,
                            and inference), or False otherwise.
                - messages: str, text describing the error(s) encounte-
                            red if there are any.
        '''
        #TODO
        raise NotImplementedError('Not yet implemented.')