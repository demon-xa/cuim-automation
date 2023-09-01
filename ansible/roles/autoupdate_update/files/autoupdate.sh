#!/bin/bash

LOCKFILE=/tmp/autoupdate.lock

PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
PATH_SRC=/srv/autoupdate
PATH_DST_PROG=/srv/updater
PATH_URL="http://teamcity.grav.su/artifacts/{%type%}/{%type%}.latest_{%ver%}"
PATH_LOG=${PATH_SRC}/autoupdate.log

SOFT_TYPE=`grep -m 1 -ioP "dec|lob|kop" /opt/ptolemey/Complex/version 2> /dev/null | tail -1` # dec/lob/kop
SOFT_VER=${1:-release} # alpha/rc/release/release_stage_1
FORCE_UPDATE=${2:-false}

function log() {
    echo "$*" >> ${PATH_LOG}
    echo "$*"
}

# Необходимо обновлять старые версии ПО на второстепенных ИМ
# http://jira.grav.su/browse/DV-6593
function oldVersion() {
    # Проверяем версию в БД
    local status=`mysql -sN -e "select if(major >= 1 and minor >= 36, 1, 0) as status from ptolemey_db.current_version order by datetime desc limit 1;" 2> /dev/null`
    if [[ "${status}" =~ ^[01]$ ]]; then
        return ${status};
    fi

    # Проверяем версию в файле
    local fileVersion=/opt/ptolemey/Complex/version
    if [ ! -f ${fileVersion} ]; then
        # Файл версии отсутствует на очень старых комплексах
        return 0
    fi
    local version=`grep -m1 -ioP "^[a-z]+(\.\d+){2}" ${fileVersion} 2> /dev/null | sed 's/[^0-9]//g'`
    if [[ "${version}" =~ ^[0-9]+$ ]]; then
        if (( ${version} >= 136 )); then
            return 1
        fi
    fi
    return 0
}

# Требование А.Нестерова
# http://jira.grav.su/browse/DV-6468
function canYouRun() {
    local timeNow=`date +%s`;
    local timeStartDay=`date +%s -d \`date +'%Y-%m-%d'\``;
    local timeDelta=$((${timeNow}-${timeStartDay}));
    local timeDeltaMin=$(($timeDelta/60))

    local timeStart=$(sha256sum <<< "`hostname` `date +'%d.%m.%Y'`" | grep -ioP "^[^\s]+" | tr -d 'a-z' | grep -ioP "^\d{6,8}")
    let 'timeStart%=1440'

    local timeStop=$((${timeStart}+60))

    # printf "timeNow: ${timeNow}\ntimeStartDay: ${timeStartDay}\ntimeDelta: ${timeDelta}\ntimeDeltaMin: ${timeDeltaMin}\ntimeStart: ${timeStart}\ntimeStop: ${timeStop}\n"
    printf "Минут с начала суток: ${timeDeltaMin}\nСтарт: ${timeStart}\nСтоп: ${timeStop}\n"

    # Принудительное обновление
    if ${FORCE_UPDATE}; then
        return 0
    fi

    if ((${timeDeltaMin} > ${timeStart} && ${timeDeltaMin} < ${timeStop})); then
        return 0
    fi
    return 1
}

# Функция очистки старый данных
function clear() {
    rm -rf ${PATH_SRC}/ptolemey 2> /dev/null
}

# Функция реализует механизм скачивания файла с PATH_URL
# Проверяет код ответа сервера и, если требуется, сравнивает содержимое файла с шаблоном
function download() {
    local extension=$1
    local checkRegexp=$2
    local fileDst=/tmp/latest.${extension}

    log "Скачивание ${PATH_URL}.${extension}"
    local responce=`curl -s -w "%{http_code}" ${PATH_URL}.${extension} -o ${fileDst}`

    if [ ${responce} != 200 ]; then
        log "error: не могу скачать"
        exit 4
    fi

    if (( ${#checkRegexp} > 0 )) && [[ -z `grep -ioP "${checkRegexp}" ${fileDst} 2> /dev/null` ]]; then
        log "error: содержимое файла ${fileDst} не соответствует шаблону '${checkRegexp}'"
        exit 4
    fi
}

# Функция реализует механизм проверки наличия на комплексе архива с последней версии ПО
function need_to_download() {
    # скачиваем md5 файл и проверяем его содержимое по шаблону
    download md5 "^[a-z0-9]{32}\s+.+$"

    # если архив не найден вообще
    if [ ! -f ${PATH_SRC}/latest.tar.xz ]; then
        return 0
    fi

    # сравниваем md5 хэш скачанного ранее архива с хэшем полученным в md5 файле сборки
    local md5_tar=`md5sum ${PATH_SRC}/latest.tar.xz | grep -ioP "^[^\s]{32}"`
    local md5_new=`grep -m 1 -ioP "^[^\s]{32}" /tmp/latest.md5 2> /dev/null | tail -1`

    echo ${md5_tar} ${md5_new}

    if [ "${md5_tar}" != "${md5_new}" ]; then 
        return 0
    fi

    return 1
}

# Функция реализует механизм проверки необходимости установки новой версии ПО
function need_to_install() {
    # Файл version должен быть извлечен из архива для последующих проверок
    # Извлекается каждый раз после скачивания архива или в случае его отсутствия в ${PATH_SRC}/
    if [ ! -f ${PATH_SRC}/latest.tar.xz.version ]; then
        nice -n 19 tar -axf ${PATH_SRC}/latest.tar.xz ptolemey/Complex/version -O > ${PATH_SRC}/latest.tar.xz.version
    fi

    log "Сравнение MD5 хэша файлов version"
    local md5_version_tar=`md5sum ${PATH_SRC}/latest.tar.xz.version 2> /dev/null | grep -m 1 -ioP "^[a-z0-9]{32}"`
    local md5_version_old=`md5sum /opt/ptolemey/Complex/version 2> /dev/null | grep -m 1 -ioP "^[a-z0-9]{32}"`
    local md5_version_src=`md5sum ${PATH_SRC}/successfully.info 2> /dev/null | grep -m 1 -ioP "^[a-z0-9]{32}"`
    log "Установлена сейчас: ${md5_version_old}"
    log "Находится в архиве: ${md5_version_tar}"
    log "Последняя успешно установленная скриптом: ${md5_version_src:-none}"

    if [ "${md5_version_tar}" != ${md5_version_old} ]; then
        return 0
    fi

    # в ходе успешной установки, которая могла быть ранее, в каталоге PATH_SRC должен появиться файл с информацией об успешно установленной версией
    # по сути, все три файла версий: установленная, в архиве и в каталоге PATH_SRC должны совпадать
    # такой механизм выбран чтобы не привязываться к логам программистов т.к. они не стандартизированы и их формат может измениться в любое время
    # также нельзя доверять файлу version в каталоге с установленным ПО т.к он перезаписывается на начальном этапе работы скрипта программистов и нет гарантий, что их скрипт завершил работу успешно
    if [ "${md5_version_tar}" != "${md5_version_src}" ] && [ "${md5_version_src}" != "none" ]; then
        return 0
    fi

    return 1
}

# Функция реализует установку ПО
# По сути только отслеживание кода овтета скрипта программистов
function install() {
    clear

    log "Остановка ПО"
    service supervisord stop 2> /dev/null

    local backupScript=/opt/ptolemey/scripts/backup.sh
    if [ -f ${backupScript} ]; then
        log "Создание резервной копии конфигов ПО"
        ${backupScript} make &> /dev/null
    fi

    log "Распаковка ${PATH_SRC}/latest.tar.xz"
    tar -xf ${PATH_SRC}/latest.tar.xz -C ${PATH_SRC} 2> /dev/null
    if (( $? > 0 )); then
        log "Ошибка распаковки архива"
        exit 5
    fi

    # Скачанный архив может быть патчем
    if [ -f ${PATH_SRC}/ptolemey/unpack.py ]; then
        log "Найден скрипт unpack.py, применяем патч"
        cd ${PATH_SRC}/ptolemey
        ${PATH_SRC}/ptolemey/unpack.py &> ${PATH_SRC}/unpack.log

        if (( $? != 0 )); then
            log "Скрипт ${PATH_SRC}/ptolemey/unpack.py завершил работу с ошибкой"
            return 1
        fi        
    fi

    # Запускаем обновление
    if [ ! -f ${PATH_SRC}/ptolemey/Complex/update_complex.py ]; then
        log "Не найден файл ${PATH_SRC}/ptolemey/Complex/update_complex.py"
        return 1
    else
        log "Запуск update_complex.py"
        cd ${PATH_SRC}/ptolemey/Complex
        ${PATH_SRC}/ptolemey/Complex/update_complex.py &> ${PATH_SRC}/update_complex.py.log

        if (( $? == 0 )); then
            cp /opt/ptolemey/Complex/version ${PATH_SRC}/successfully.info
            return 0
        fi
    fi

    return 1
}

# Функция делает копию архива с пакетом обновления для последующего использования отелом разработки
# Костыль во благо общества, только хз какого
function copy_to_proger() {
    local realName=`grep -ioP "[^\s\/]+\.tar\.xz$" /tmp/latest.md5 2> /dev/null | head -1`
    if [ -z "${realName}" ]; then
        log "Реальное имя архива не выяснено"
        return 0
    fi
    mkdir -p ${PATH_DST_PROG}
    cp ${PATH_SRC}/latest.tar.xz ${PATH_DST_PROG}/${realName} 2> /dev/null
    return $?
}

# Не запускаем скрипт если найден /opt/ptolemey/Complex/special.lock
if [ -f /opt/ptolemey/Complex/special.lock ]; then
    echo "Найден special.lock файл, скрипт остановлен"
    exit 1
fi

# Не запускаем скрипт если его копия уже запущена
if [ -e ${LOCKFILE} ] && kill -0 `cat ${LOCKFILE}` 2>/dev/null; then
    exit 1
fi

trap "rm -f ${LOCKFILE}; exit" INT TERM EXIT
echo $$ > ${LOCKFILE}

# Не запускаем скрипт если не пришло время обновления
if ! canYouRun; then
    echo "error: запрет запуска автообновления по времени"
    rm -f ${LOCKFILE}
    exit 1
fi

date > ${PATH_LOG}

# Не запускаем скрипт есть мало места на диске
if (( `df | grep -ioP "\d+%\s/$" | grep -ioP "\d+"` > 90 )); then
    log "error: менее 10% свободного места на диске, обновление остановлено"
    rm -f ${LOCKFILE}
    exit 1
fi

# Не запускаем скрипт если работает ПНР
supervisord_conf=/opt/ptolemey/Complex/Supervisor/supervisord.conf.d
if [ ! -d ${supervisord_conf} ]; then
    log "error: не найден каталог ${supervisord_conf}"
    rm -f ${LOCKFILE}
    exit 1
else
    supervisord_conf_active=`cd -P ${supervisord_conf}; pwd | grep -ioP "[^/]+$"`
    if [ "${supervisord_conf_active}" != "Regular" ]; then
        log "error: на комплексе работает ПНР"
	    rm -f ${LOCKFILE}
        exit 1
    fi
fi

# Не запускаем скрипт, если мы на второстепенном ИМ
if [ ! -f ${supervisord_conf}/CrossroadProcessingServer.conf ] && ! oldVersion; then
    log "error: обновление второстепенных ИМ запрещено"
    rm -f ${LOCKFILE}
    exit 1
fi

# Создание корневого каталога для работы скрипта
if [ ! -d ${PATH_SRC} ]; then
    mkdir -p ${PATH_SRC}
fi

# Проверка корректности переданных данных о версии и типе ПО
if [[ ! ${SOFT_TYPE} =~ ^dec|lob|kop$ ]]; then
    log "error: ошибочный тип ПО"
    rm -f ${LOCKFILE}
    exit 2
fi

if [[ ! ${SOFT_VER} =~ ^alpha|rc|release|release_stage_1$ ]]; then
    log "error: ошибочная версия ПО"
    rm -f ${LOCKFILE}
    exit 3
fi

# Восстановление PATH_URL
PATH_URL=${PATH_URL//\{%type%\}/${SOFT_TYPE}}
PATH_URL=${PATH_URL//\{%ver%\}/${SOFT_VER}}

# Скачиваем архив с новой версией ПО, если в этом есть необходимость
if need_to_download; then
    log "Найдена более актуальная версия ПО ${SOFT_TYPE^^} сборка ${SOFT_VER^^}"
    cat /tmp/latest.md5 2> /dev/null
    download tar.xz
    mv /tmp/latest.tar.xz ${PATH_SRC}/latest.tar.xz
    # Файл version извлекается каждый раз после скачивания нового архива
    # Используется для последующего сравнения в проверке необходимости установки обновления
    nice -n 19 tar -axf ${PATH_SRC}/latest.tar.xz ptolemey/Complex/version -O > ${PATH_SRC}/latest.tar.xz.version
else
    log "Самая последняя версия ПО уже была скачана ранее"
fi

if need_to_install; then
    if install; then
        log "Обновленые выполнено успешно"
        log "Делаем копию архива для отдела разработки"
        if copy_to_proger; then
            log "Копия сохранена в каталоге ${PATH_DST_PROG}"
        else
            log "Не удалось сделать копию"
        fi
    else
        log "Обновление не выполнено, лог работы скрипта программистов схранен в ${PATH_SRC}/update_complex.py.log"
    fi
else
    log "Самая последняя версия ПО уже была установлена ранее"
fi

clear

rm -f ${LOCKFILE}