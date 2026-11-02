# NTnRoute.AI

[English](README.md) | [Indonesia](README.id.md) | [Español](README.es.md) | [日本語](README.ja.md) | [Deutsch](README.de.md)

Motor de gestión de dispositivos de red por SSH para agentes de IA: un pequeño inventario de dispositivos, ejecución segura de CLI, copia de seguridad de configuraciones y cambios de configuración **con puerta de aprobación** y rollback automático — junto con un conjunto de skills de [Hermes Agent](https://hermes-agent.nousresearch.com) que enseñan al agente a usarlo de forma responsable.

## Qué hace

- **Inventario** — registra un dispositivo una vez (`ntn add`); el motor prueba la conexión SSH, obtiene el hostname y la configuración en ejecución, y solo entonces lo guarda. Todo se almacena en un archivo JSON plano (`~/.ntnroute/devices.json`, modo 600) que sobrevive a los reinicios del agente.
- **Acceso de solo lectura** — `ntn exec` ejecuta comandos tipo `show ...` y devuelve la transcripción.
- **Copia de seguridad** — `ntn sync` guarda la configuración en ejecución en el inventario y en un archivo de respaldo con marca de tiempo.
- **Cambios de configuración con puerta** — `ntn config` ejecuta: snapshot previo → aplicar → guardar → post-verificación (cada línea del script debe aparecer en la nueva configuración) → actualización del inventario. ¿Dispositivo inaccesible antes del cambio? Aborta. ¿El dispositivo rechaza una línea? Se reporta el fallo y el inventario queda intacto.
- **Rollback** — cada cambio guarda un checkpoint; `ntn rollback` aplica el script de deshacer almacenado.
- **Registro de auditoría** — `ntn audit` muestra las últimas operaciones.

El motor es solo bash + jq + OpenSSH — sin Python, sin agentes, sin demonios.
Los scripts auxiliares (`triage`, `rollback_gen`, `ios_session.sh`) también son
bash + awk; solo las compuertas de auditoría opcionales (`cfg_audit.py`,
`sec_audit.py`) usan Python estándar.

## Plataformas soportadas

| Fabricante | Modo | Obtener config | Guardar |
|---|---|---|---|
| Cisco IOS | PTY interactivo | `show running-config` | `write memory` |
| Huawei VRP | PTY interactivo | `display current-configuration` | `save` + confirmación |
| Aruba / Arista / Ruijie | PTY interactivo | `show running-config` | `write memory` |
| Juniper Junos | PTY interactivo | `show configuration \| display set` | `commit` (dentro del modo config) |
| Fortinet FortiGate | PTY interactivo | `show full-configuration` | automático (se aplica al enviar) |
| MikroTik RouterOS | modo exec (`ssh -T`) | `/export` | automático |

La criptografía legacy (imágenes Cisco antiguas) está soportada: `diffie-hellman-group14-sha1`, `ssh-rsa`, `aes128-cbc`, `hmac-sha1` se negocian cuando hace falta.

## Adaptarse a nuevos fabricantes

El comportamiento por marca vive en `~/.ntnroute/brands.json` — edítalo para soportar un fabricante que el motor no conoce, o para sobrescribir uno integrado (cambios de firmware incluidos). Una entrada basta:

```json
{
  "zte": {
    "paging": "terminal length 0",
    "config_enter": "configure terminal",
    "config_leave": "end",
    "save_lines": ["write memory"],
    "config_show": "show running-config",
    "hostname_show": "show running-config | include hostname",
    "hostname_field": "hostname",
    "err_pattern": "(^%|Invalid input)"
  }
}
```

Campos: `paging`, `secret_cmd`, `config_enter`, `config_leave`, `save_lines` (array), `save_delay`, `config_show`, `hostname_show`, `hostname_field` (`hostname`|`sysname`|`host-name`|`colon`), `err_pattern` (grep -E), `negate_prefix` (usado por `rollback_gen`). Las marcas desconocidas sin perfil usan valores genéricos tipo Cisco y se saltan el paso de guardado. El instalador nunca sobrescribe tu `brands.json`.

## Instalación

Requisitos: Linux/macOS con `bash`, `jq`, `ssh` (OpenSSH).

```bash
git clone https://github.com/Dandi41/ntnroute.git
cd ntnroute
./install.sh
```

El instalador:

1. comprueba `jq` y `ssh`,
2. instala el motor en `~/.ntnroute/ntn` (modo 700) y crea el enlace simbólico `~/.local/bin/ntn`,
3. crea `~/.ntnroute/` con un inventario vacío (modo 600),
4. si usas [Hermes Agent](https://hermes-agent.nousresearch.com), copia las cinco skills a `~/.hermes/skills/networking/`.

## Inicio rápido

```bash
# registra un dispositivo (primero prueba la conexión; si falla, no se guarda)
ntn add 10.0.0.5 22 admin S3cr3t! Router Cisco enablepass123

ntn list                # inventario numerado
ntn show 1              # detalles + config almacenada
ntn ping 1              # comprobación ICMP
ntn exec 1 'show ip interface brief' 'show ip route'
ntn sync all            # obtiene la running-config de todos los dispositivos
ntn audit 10            # últimas 10 operaciones
```

Un cambio de configuración es siempre: plan → aprobación → aplicar → verificar. La skill `network-change-management` impone la puerta de aprobación y genera el script de rollback antes de tocar el dispositivo.

## Las skills incluidas

| Skill | Propósito |
|---|---|
| `ntnroute` | Reglas de flujo de trabajo del motor `ntn` (inventario, exec, config, rollback) |
| `network-device-cli` | Mecánica de sesiones SSH por fabricante, cripto legacy, análisis de credenciales |
| `network-change-management` | Puerta de plan/aprobación, auditoría de blast radius, generación de rollback |
| `network-troubleshooting` | Diagnóstico OSI-first con referencias de comandos por fabricante |
| `network-security-audit` | Auditoría de hardening local + perímetro de las configuraciones |

## Notas de seguridad

- Las contraseñas se guardan **en texto plano** en `~/.ntnroute/devices.json` (modo 600, solo el propietario). Es una decisión consciente para una herramienta de laboratorio — no la apuntes a producción si eso es inaceptable.
- `ntn show <ref>` oculta las contraseñas por defecto; `--reveal` las muestra.
- `devices.json` y `backups/` están en .gitignore. **Nunca los subas al repositorio.**

## Estado y honestidad

Probado de extremo a extremo en dispositivos reales: Cisco IOS 15.4 y MikroTik RouterOS 7.18.2 (add/list/show/exec/sync, config + post-verificación, rollback, comandos destructivos, guardia de dispositivo inaccesible, guardia de error del dispositivo). Las demás marcas (Huawei VRP, Arista EOS, Aruba AOS-CX, Ruijie RGOS, Juniper Junos, Fortinet FortiGate) se verificaron igual contra CLIs de fabricante emulados (arnés de pruebas local, no forma parte del toolkit).

Las rutas de código para Huawei, Aruba, Arista, Ruijie y Juniper existen pero **no** se han probado aún contra hardware real — trátalas como experimentales y reporta problemas en Issues.

## Apoyar

Si ntnroute te ahorra tiempo, puedes invitar al creador a un lemper 🙂 — un bocadillo indonesio de arroz glutinoso: **[tako.id/Lemper41](https://tako.id/Lemper41)**

Encuéntrame en [Instagram](https://www.instagram.com/sdandi_41/) y [LinkedIn](https://www.linkedin.com/in/dandi-suryadi-a29276253/).

## Licencia

[MIT](LICENSE) © Dandi Suryadi
