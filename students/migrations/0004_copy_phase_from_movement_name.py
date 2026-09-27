from django.db import migrations


def copy_movement_name_to_phase(apps, schema_editor):
    AnalysisMovement = apps.get_model('students', 'AnalysisMovement')
    for row in AnalysisMovement.objects.all():
        if not row.phase and row.movement_name:
            row.phase = row.movement_name
            row.save(update_fields=['phase'])


class Migration(migrations.Migration):

    dependencies = [
        ('students', '0003_rich_analysis_frames'),
    ]

    operations = [
        migrations.RunPython(copy_movement_name_to_phase, migrations.RunPython.noop),
    ]
