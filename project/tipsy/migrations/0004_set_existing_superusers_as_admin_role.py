from django.db import migrations


def set_superusers_to_admin_role(apps, schema_editor):
    CustomUser = apps.get_model('tipsy', 'CustomUser')
    CustomUser.objects.filter(is_superuser=True).update(role='ADMIN')


def revert_superusers_to_customer_role(apps, schema_editor):
    CustomUser = apps.get_model('tipsy', 'CustomUser')
    CustomUser.objects.filter(is_superuser=True, role='ADMIN').update(role='CUSTOMER')


class Migration(migrations.Migration):

    dependencies = [
        ('tipsy', '0003_customuser_vendor_status_alter_customuser_role'),
    ]

    operations = [
        migrations.RunPython(set_superusers_to_admin_role, revert_superusers_to_customer_role),
    ]
