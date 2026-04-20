from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0002_document_is_locked_document_locked_at_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='document',
            name='email_sent_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
