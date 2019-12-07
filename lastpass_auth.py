import lastpass
import ipywidgets as widgets
from IPython.display import clear_output, display
from ipywidgets import VBox

class LastpassAuth:
    def __init__(self, username = ""):
        # to save widget state
        self.username = username
        self.password_widget = None
        self.otp_widget = None
        self.vbox = None
        self.vault = None

        self.authorize_widget()

    def authorize_widget(self):
        self.username_widget = widgets.Text(description="Username:", value=self.username)
        self.password_widget = widgets.Password(description="Password:")
        self.otp_widget = widgets.Text(description="OTP:")

        login_button = widgets.Button(description="Login")

        login_button.on_click(self.on_login_button_click)
        self.vbox = VBox([self.username_widget, self.password_widget, self.otp_widget, login_button])
        display(self.vbox)

    def on_login_button_click(self, button):
        username = self.username_widget.value
        password = self.password_widget.value
        otp = self.otp_widget.value

        print("Logging onto lastpass ...")
        self.vault = lastpass.Vault.open_remote(username, password, otp)
        
        self.password_widget.value = ""
        self.otp_widget.value = ""
        display(self.vbox)
    def get_credentials(self, key):
        for i in self.vault.accounts:
            if i.name.decode("utf-8") == key:
                return i.notes.decode("utf-8")
        print("Could not find key in Lastpass")
