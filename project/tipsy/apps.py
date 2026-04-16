from django.apps import AppConfig


class TipsyConfig(AppConfig):
    name = 'tipsy'
    
    def ready(self):
        import tipsy.signals
