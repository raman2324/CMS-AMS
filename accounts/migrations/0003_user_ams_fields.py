import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def rename_issuer_to_finance_executive(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    User.objects.filter(role='issuer').update(role='finance_executive')


def reverse_finance_executive_to_issuer(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    User.objects.filter(role='finance_executive').update(role='issuer')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_alter_user_role'),
    ]

    operations = [
        # 1. Widen role field to fit new values and update choices
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('admin', 'Admin'),
                    ('finance_head', 'Finance Head'),
                    ('finance_executive', 'Finance Executive'),
                    ('manager', 'Manager'),
                    ('employee', 'Employee'),
                    ('viewer', 'Viewer'),
                    ('it', 'IT'),
                ],
                default='finance_executive',
                max_length=20,
            ),
        ),
        # 2. Data migration: issuer → finance_executive
        migrations.RunPython(
            rename_issuer_to_finance_executive,
            reverse_code=reverse_finance_executive_to_issuer,
        ),
        # 3. Add AMS org-hierarchy fields
        migrations.AddField(
            model_name='user',
            name='reports_to',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='reports',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='offboarded_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
