from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_merge_0004_alter_user_role_0004_remove_it_role'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserPermission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('permission', models.CharField(choices=[('view_documents', 'View Documents'), ('generate_letters', 'Generate Letters'), ('download_pdfs', 'Download PDFs'), ('file_uploads', 'File Uploads'), ('submit_requests', 'Submit Requests'), ('approve_requests', 'Approve Requests'), ('view_all_requests', 'View All Requests'), ('contract_lens', 'Contract Lens')], max_length=30)),
                ('state', models.CharField(choices=[('default', 'Default'), ('allow', 'Allow'), ('deny', 'Deny')], default='default', max_length=10)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='permission_overrides', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'User Permission Override',
                'unique_together': {('user', 'permission')},
            },
        ),
    ]
