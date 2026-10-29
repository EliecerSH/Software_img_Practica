"""
Punto de entrada del Generador de imágenes de producto (pack y tripack para marketplace).

Ejecución:
    - Modo Interfaz Gráfica (por defecto si no se pasan argumentos):
        python main.py
        o hacer doble clic en 'iniciar_software.bat'

    - Modo Consola / Línea de Comandos:
        python main.py --pair 30-CRU/65-CAF --formato pack
        python main.py --pair 30-CRU --formato tripack     (el mismo producto repetido 3 veces)
        python main.py --list codigos.txt
        python main.py foto1.jpg foto2.jpg -o resultado.jpg
"""
import sys


def main():
    # Si no se pasan argumentos o se pasa --gui, arrancar la interfaz gráfica
    if len(sys.argv) == 1 or (len(sys.argv) == 2 and sys.argv[1].lower() in ("--gui", "-g")):
        try:
            import app_gui
            app_gui.main()
            return
        except Exception as e:
            print(f"Error al iniciar interfaz gráfica: {e}", file=sys.stderr)
            print("Iniciando en modo consola...", file=sys.stderr)

    # De lo contrario, usar el CLI de pipeline
    import pipeline
    pipeline.main()


if __name__ == "__main__":
    main()
