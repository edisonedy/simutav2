from django.contrib import admin

from .models import (
    AccionSugeridaSimulacion,
    CondicionExitoSimulacion,
    ConceptoEsperadoRonda,
    CriterioEvaluacion,
    DecisionConfigurada,
    EscenarioSimulacion,
    IndicadorSimulacion,
    IntentoSimulacion,
    PasoSimulacion,
    PerfilMateriaIA,
    PlantillaConcepto,
    PlantillaIndicador,
    PlantillaRestriccion,
    PlantillaRonda,
    PlantillaSimulacion,
    RestriccionSimulacion,
    Simulacion,
)

admin.site.register(Simulacion)
admin.site.register(PerfilMateriaIA)
admin.site.register(PlantillaSimulacion)
admin.site.register(PlantillaRonda)
admin.site.register(PlantillaIndicador)
admin.site.register(PlantillaRestriccion)
admin.site.register(PlantillaConcepto)
admin.site.register(IndicadorSimulacion)
admin.site.register(RestriccionSimulacion)
admin.site.register(CriterioEvaluacion)
admin.site.register(AccionSugeridaSimulacion)
admin.site.register(CondicionExitoSimulacion)
admin.site.register(ConceptoEsperadoRonda)
admin.site.register(EscenarioSimulacion)
admin.site.register(DecisionConfigurada)
admin.site.register(IntentoSimulacion)
admin.site.register(PasoSimulacion)
