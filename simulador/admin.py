from django.contrib import admin

from .models import (
    AccionSugeridaSimulacion,
    ActividadMateria,
    Asignacion,
    CondicionExitoSimulacion,
    ConceptoEsperadoRonda,
    CriterioEvaluacion,
    DecisionConfigurada,
    EscenarioSimulacion,
    EventoSimulacion,
    IndicadorSimulacion,
    IntentoSimulacion,
    MatrizEvaluacionCaso,
    OpcionCasoSimulacion,
    OpcionRondaSimulacion,
    PasoSimulacion,
    PerfilMateriaIA,
    PlantillaConcepto,
    PlantillaIndicador,
    PlantillaRestriccion,
    PlantillaRonda,
    PlantillaSimulacion,
    PistaTutor,
    Equipo,
    RecursoSimulacion,
    RecursoSimulacionArchivo,
    ResultadoAprendizaje,
    RestriccionSimulacion,
    RondaSimulacion,
    Seccion,
    Simulacion,
    TemaMateria,
)


class OpcionRondaInline(admin.TabularInline):
    model = OpcionRondaSimulacion
    extra = 0


class ArchivoRondaInline(admin.TabularInline):
    model = RecursoSimulacionArchivo
    fk_name = 'ronda'
    extra = 0


@admin.register(RondaSimulacion)
class RondaSimulacionAdmin(admin.ModelAdmin):
    list_display = ['simulacion', 'numero', 'titulo', 'tipo_respuesta', 'puntaje_maximo']
    list_filter = ['tipo_respuesta', 'simulacion__materia_malla__materia']
    search_fields = ['titulo', 'situacion', 'simulacion__titulo']
    inlines = [OpcionRondaInline, ArchivoRondaInline]


@admin.register(RecursoSimulacionArchivo)
class RecursoSimulacionArchivoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'simulacion', 'ronda', 'tipo', 'orden']
    list_filter = ['tipo']
    search_fields = ['nombre', 'simulacion__titulo']

admin.site.register(Simulacion)
admin.site.register(TemaMateria)
admin.site.register(ActividadMateria)
admin.site.register(PerfilMateriaIA)
admin.site.register(PlantillaSimulacion)
admin.site.register(PlantillaRonda)
admin.site.register(PlantillaIndicador)
admin.site.register(PlantillaRestriccion)
admin.site.register(PlantillaConcepto)
admin.site.register(IndicadorSimulacion)
admin.site.register(RecursoSimulacion)
admin.site.register(RestriccionSimulacion)
admin.site.register(CriterioEvaluacion)
admin.site.register(MatrizEvaluacionCaso)
admin.site.register(OpcionCasoSimulacion)
admin.site.register(AccionSugeridaSimulacion)
admin.site.register(CondicionExitoSimulacion)
admin.site.register(EventoSimulacion)
admin.site.register(ConceptoEsperadoRonda)
admin.site.register(EscenarioSimulacion)
admin.site.register(DecisionConfigurada)
admin.site.register(IntentoSimulacion)
admin.site.register(PasoSimulacion)
admin.site.register(PistaTutor)
admin.site.register(ResultadoAprendizaje)
admin.site.register(Seccion)
admin.site.register(Asignacion)
admin.site.register(Equipo)
