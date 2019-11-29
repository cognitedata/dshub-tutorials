import os

import ipywidgets as widgets
from cognite.client import CogniteClient
from cognite.client.exceptions import CogniteAPIError, CogniteAPIKeyError
from IPython.display import clear_output, display
from ipywidgets import VBox


class Auth:
    def __init__(
        self,
        api_key_variable_name="COGNITE_API_KEY",
        project="",
        client_name="context_notebook_templates",
        on_authorized_api_key=None,
    ):
        """
        Widget to get api-key and project into the environment and create a cognite_client as attribute.
        Args:
            api_key_variable_name (str) the name of the variable for the api-key in .env if any to get as a default
                in the widget.
            project (str): project shown as default in the widget.
            client_name (str): name to define the  unique applications/scripts running on top of CDF.
            on_authorized_api_key (function (cognite_client: CogniteClient, project: str) -> Any ): callback function
            called when user clicks on the widget button and if authorization is succeeded.
        """
        self.api_key_variable_name = api_key_variable_name
        self.project = project
        self.client_name = client_name
        self.on_authorized_api_key = on_authorized_api_key

        self.api_key = None
        self.cognite_client = None

        # to save widget state
        self.project_widget = None
        self.api_key_widget = None
        self.vbox = None

        self.authorize_widget()

    def authorize_widget(self):

        self.project_widget = widgets.Text(description="Project:", value=self.project)
        self.api_key_widget = widgets.Password(description="API-key:", placeholder="Leave empty to use .env")

        submit_button = widgets.Button(description="Submit")

        submit_button.on_click(self.handle_submit_api_key)
        self.vbox = VBox([self.project_widget, self.api_key_widget, submit_button])
        display(self.vbox)

    def test_api_key(self):
        """ Check if key is a valid API-key and if it matches the project.
        """

        cognite_client = CogniteClient(api_key=self.api_key, project=self.project, client_name=self.client_name)
        login_status = cognite_client.login.status().logged_in
        project_from_key = cognite_client.login.status().project

        if not login_status:
            clear_output()
            display(self.vbox)
            raise CogniteAPIKeyError("The authentication was not successful. The api-key is wrong.")

        elif project_from_key != self.project:
            clear_output()
            display(self.vbox)
            raise CogniteAPIKeyError("The authentication was not successful. The project name is wrong.")
        try:
            cognite_client.assets.list(root=True)
        except CogniteAPIError:
            clear_output()
            display(self.vbox)
            raise CogniteAPIKeyError("The authentication was not successful. Something else is wrong.")

        self.cognite_client = cognite_client
        return True

    def handle_submit_api_key(self, button):
        """
        Test the api-key together with project for being correct. Proceed with on_authorized_api_key if defined.

        button (widget): Not used, part of callback signature
        """

        self.project = self.project_widget.value
        self.api_key = self.api_key_widget.value
        os.environ["COGNITE_API_KEY"] = self.api_key
        os.environ["COGNITE_PROJECT"] = self.project
        os.environ["COGNITE_CLIENT_NAME"] = "DataStudio"
        print("Now using key ", os.environ["COGNITE_API_KEY"])
        
        self.test_api_key()

        clear_output()
        display(self.vbox)
        # os.environ["COGNITE_API_KEY"] = self.api_key
        # os.environ["COGNITE_PROJECT"] = self.project
        # print("Saved COGNITE_API_KEY, COGNITE_PROJECT as environment variables.")

        if self.on_authorized_api_key:
            self.on_authorized_api_key(cognite_client=self.cognite_client, project=self.project)