from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ams_approvals', '0005_add_finance_approver'),
    ]

    operations = [
        migrations.AddField(
            model_name='approvalrequest',
            name='renewal_expires_on',
            field=models.DateField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='approvalrequest',
            name='renewal_cost',
            field=models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True),
        ),
    ]
