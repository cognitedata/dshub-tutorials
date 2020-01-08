import os

import ipywidgets as widgets
from cognite.client import CogniteClient
from cognite.client.exceptions import CogniteAPIError, CogniteAPIKeyError
from IPython.display import clear_output, display
from ipywidgets import VBox


class ClientApiKeyWidget:
    def __init__(
        self,
        api_key_name="COGNITE_API_KEY",
        project="",
        client_name="context_notebook_templates"
    ):
        """
        Widget to get api-key and project into the environment and create a cognite_client as attribute.
        Args:
            api_key_name (str) the name of the variable for the api-key in .env if any to get as a default
                in the widget.
            project (str): project shown as default in the widget.
            client_name (str): name to define the  unique applications/scripts running on top of CDF.
        """
        self.api_key_name = api_key_name
        self.project = project
        self.client_name = client_name

        self.api_key = None
        self.cognite_client = None

        # to save widget state
        self.project_widget = None
        self.api_key_widget = None
        self.vbox = None

        self.authorize_widget()

    def authorize_widget(self):

        self.project_widget = widgets.Text(description="Project:", value=self.project)
        self.api_key_widget = widgets.Password(description="API-key:", placeholder="Leave empty to look for key .env")

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
        Test the api-key together with project for being correct.
        button (widget): Not used, part of callback signature
        """

        if self.project_widget.value == "":
            self.project = self.project_widget.placeholder
        else:
            self.project = self.project_widget.value

        if self.api_key_widget.value == "":
            self.api_key = os.environ.get(self.api_key_name, "")
        else:
            self.api_key = self.api_key_widget.value

        self.test_api_key()

        clear_output()
        display(self.vbox)
        if os.environ.get(self.api_key_name) is None:
            os.environ[self.api_key_name] = self.api_key
            print(f"Saved '{self.api_key_name}' as environment variables.")
        print(f"API-key: '{self.api_key_name}' in .env for \nproject: '{self.project}' \nis valid.")
