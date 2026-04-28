from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0012_add_user_created_deactivated_events"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("document.generated", "Document Generated"),
                    ("document.downloaded", "Document Downloaded"),
                    ("document.voided", "Document Voided"),
                    ("document.viewed", "Document Viewed"),
                    ("document.access_denied", "Document Access Denied"),
                    ("document.locked", "Document Locked"),
                    ("document.unlocked", "Document Unlocked"),
                    ("document.generation_failed", "Document Generation Failed"),
                    ("template.published", "Template Published"),
                    ("template.deleted", "Template Deleted"),
                    ("user.created", "User Created"),
                    ("user.role_changed", "User Role Changed"),
                    ("user.deactivated", "User Deactivated"),
                    ("company.created", "Company Created"),
                    ("company.updated", "Company Updated"),
                    ("audit.flag.template_issuer_overlap", "Template-Issuer Overlap Flag"),
                    ("reconciliation.mismatch", "Reconciliation Mismatch"),
                    ("reconciliation.ok", "Reconciliation OK"),
                    ("upload.created", "File Uploaded"),
                    ("upload.viewed", "File Viewed"),
                    ("upload.downloaded", "File Downloaded"),
                    ("upload.deleted", "File Deleted"),
                    ("contractlens.extracted", "ContractLens: PDF Extracted"),
                    ("contractlens.confirmed", "ContractLens: Data Confirmed"),
                    ("contractlens.downloaded", "ContractLens: File Downloaded"),
                    ("contractlens.group_analysed", "ContractLens: Group Analysed"),
                    ("contractlens.merged", "ContractLens: Contracts Merged"),
                ],
                db_index=True,
                max_length=100,
            ),
        ),
    ]
