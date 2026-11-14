import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import qs.Commons as Commons

Item {
    id: root
    property var shell: null
    property var manifest: null
    property bool opened: false
    property bool remote: false
    property var items: []
    property var selected: null
    property string status: ""
    property string qrPath: ""
    property int page: 1
    property bool more: false
    property bool failed: false
    property string operation: ""
    readonly property bool busy: action.running || listing.running
    Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }

    function open(payload) {
        opened = true
        let request = {}
        try { request = typeof payload === "string" ? JSON.parse(payload) : (payload || {}) } catch (e) {}
        if (!busy) {
            if (typeof request.query === "string" && request.query.trim()) {
                query.text = request.query.slice(0, 200)
                search(1)
            } else loadLibrary()
        }
        Qt.callLater(function() { query.forceActiveFocus() })
    }
    function close() { opened = false }
    function dismiss() {
        opened = false
        if (shell && typeof shell.hide === "function") shell.hide("io.github.dkgamer02ai.wallpaper-engine")
    }
    function toggle() { if (opened) dismiss(); else open("{}") }
    function loadLibrary() {
        if (busy) return
        remote = false
        selected = null
        status = ""
        listing.command = ["omarchy-we", "list", "--json"]
        listing.running = true
    }
    function search(p) {
        if (busy) return
        remote = true
        page = p
        selected = null
        failed = false
        status = strings.t("searching")
        listing.command = ["omarchy-we", "search", query.text, "--page", String(page), "--json"]
        listing.running = true
    }
    function perform(verb, value) {
        if (busy) return
        operation = verb
        failed = false
        qrPath = ""
        status = strings.t(verb === "login" ? "connecting" : verb === "assets" ? "assetsWorking" : verb === "download" ? "downloading" : "working")
        action.command = ["omarchy-we", verb]
        if (value) action.command.push(String(value))
        action.command.push("--json")
        action.running = true
    }
    function acceptEvent(line) {
        try {
            var event = JSON.parse(line)
            if (event.event === "qr") {
                qrPath = "file://" + event.path
                status = strings.t("scan")
            } else if (event.message) status = String(event.message).slice(0, 1800)
        } catch (e) {}
    }

    Process {
        id: listing
        stdout: StdioCollector { id: listOutput }
        stderr: StdioCollector { id: listError }
        onExited: function(code) {
            if (code !== 0) {
                failed = true
                status = listError.text.slice(0, 1800)
                return
            }
            try {
                var result = JSON.parse(listOutput.text)
                items = Array.isArray(result) ? result : result.items
                more = !Array.isArray(result) && result.more
                status = items.length ? "" : strings.t(remote ? "noResults" : "empty")
            } catch (e) {
                failed = true
                status = strings.t("badResponse")
            }
        }
    }
    Process {
        id: action
        stdout: SplitParser { onRead: data => root.acceptEvent(data) }
        stderr: StdioCollector { id: actionError }
        onExited: function(code) {
            qrPath = ""
            failed = code !== 0
            if (code !== 0) status = actionError.text.slice(0, 1800) || strings.t("cancelled")
            if (code === 0 && operation === "download") {
                var copy = items.slice()
                for (var i = 0; i < copy.length; i++) {
                    if (selected && copy[i].id === selected.id) {
                        copy[i] = Object.assign({}, copy[i], { installed: true })
                        selected = copy[i]
                    }
                }
                items = copy
            }
            if (code === 0 && operation === "set") {
                var updated = items.slice()
                for (var j = 0; j < updated.length; j++) updated[j] = Object.assign({}, updated[j], { current: selected && updated[j].id === selected.id })
                items = updated
            }
        }
    }

    component ActionButton: Rectangle {
        id: control
        property string label: ""
        property bool active: false
        signal clicked()
        implicitWidth: caption.implicitWidth + 26
        implicitHeight: 36
        radius: 6
        color: active ? Commons.Color.accent : (mouse.containsMouse ? Qt.alpha(Commons.Color.foreground, .14) : Qt.alpha(Commons.Color.foreground, .06))
        opacity: enabled ? 1 : .4
        border.width: activeFocus ? 2 : 1
        border.color: activeFocus ? Commons.Color.accent : Qt.alpha(Commons.Color.foreground, .18)
        activeFocusOnTab: true
        Accessible.role: Accessible.Button
        Accessible.name: label
        Keys.onReturnPressed: clicked()
        Keys.onSpacePressed: clicked()
        Text {
            id: caption
            anchors.centerIn: parent
            textFormat: Text.PlainText
            text: control.label
            color: control.active ? Commons.Color.background : Commons.Color.foreground
            font.pixelSize: 13
        }
        MouseArea { id: mouse; anchors.fill: parent; hoverEnabled: true; onClicked: control.clicked() }
    }

    PanelWindow {
        id: panel
        visible: root.opened
        anchors { top: true; bottom: true; left: true; right: true }
        color: "transparent"
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.namespace: "omarchy-wallpaper-workshop"
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
        Rectangle { anchors.fill: parent; color: "#a0000000" }
        Rectangle {
            anchors.centerIn: parent
            width: Math.min(parent.width - 48, 1120)
            height: Math.min(parent.height - 48, 780)
            color: Commons.Color.background
            border.color: Qt.alpha(Commons.Color.foreground, .25)
            radius: 12
            Keys.onEscapePressed: root.dismiss()
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 24
                spacing: 16
                RowLayout {
                    Layout.fillWidth: true
                    Text { textFormat: Text.PlainText; text: "Wallpaper Engine"; color: Commons.Color.foreground; font.pixelSize: 25; font.weight: Font.DemiBold }
                    Item { Layout.fillWidth: true }
                    ActionButton { label: strings.t("login"); enabled: !busy; onClicked: root.perform("login", "") }
                    ActionButton { label: strings.t("assets"); enabled: !busy; onClicked: root.perform("assets", "") }
                    ActionButton { label: strings.t("close"); onClicked: root.dismiss() }
                }
                RowLayout {
                    Layout.fillWidth: true
                    ActionButton { label: strings.t("library"); active: !remote; enabled: !busy; onClicked: root.loadLibrary() }
                    TextField {
                        id: query
                        Layout.fillWidth: true
                        placeholderText: strings.t("searchPlaceholder")
                        maximumLength: 200
                        color: Commons.Color.foreground
                        placeholderTextColor: Commons.Color.muted
                        selectByMouse: true
                        enabled: !busy
                        background: Rectangle { color: Qt.alpha(Commons.Color.foreground, .05); radius: 6; border.color: Qt.alpha(Commons.Color.foreground, .25) }
                        onAccepted: root.search(1)
                    }
                    ActionButton { label: strings.t("search"); enabled: !busy; active: remote; onClicked: root.search(1) }
                }
                Text {
                    Layout.fillWidth: true
                    textFormat: Text.PlainText
                    text: remote ? strings.t("remoteHint") : strings.t("localHint")
                    color: Commons.Color.muted
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                }
                GridView {
                    id: grid
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: root.items
                    cellWidth: width / Math.max(1, Math.floor(width / 240))
                    cellHeight: 175
                    ScrollBar.vertical: ScrollBar {}
                    delegate: Rectangle {
                        id: tile
                        required property var modelData
                        width: grid.cellWidth - 12
                        height: grid.cellHeight - 12
                        radius: 7
                        color: Qt.alpha(Commons.Color.foreground, .04)
                        border.width: root.selected && root.selected.id === modelData.id ? 2 : 1
                        border.color: root.selected && root.selected.id === modelData.id ? Commons.Color.accent : Qt.alpha(Commons.Color.foreground, .18)
                        activeFocusOnTab: true
                        Accessible.role: Accessible.Button
                        Accessible.name: modelData.title
                        Keys.onReturnPressed: root.selected = modelData
                        Image {
                            anchors { top: parent.top; left: parent.left; right: parent.right; margins: 8 }
                            height: 95
                            source: modelData.preview ? "file://" + modelData.preview : ""
                            sourceSize: Qt.size(400, 220)
                            asynchronous: true
                            fillMode: Image.PreserveAspectCrop
                            clip: true
                        }
                        Text {
                            visible: !modelData.preview
                            anchors.horizontalCenter: parent.horizontalCenter
                            y: 40
                            textFormat: Text.PlainText
                            text: modelData.type === "video" ? "▶" : "◈"
                            color: Qt.alpha(Commons.Color.accent, .65)
                            font.pixelSize: 32
                        }
                        Text {
                            anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 10; bottomMargin: 31 }
                            textFormat: Text.PlainText
                            text: modelData.title
                            color: Commons.Color.foreground
                            font.pixelSize: 13
                            maximumLineCount: 2
                            wrapMode: Text.WordWrap
                            elide: Text.ElideRight
                        }
                        Text {
                            anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 10 }
                            textFormat: Text.PlainText
                            text: modelData.type + "  ·  " + (modelData.current ? strings.t("applied") : modelData.installed ? strings.t("downloaded") : modelData.id)
                            color: Commons.Color.muted
                            font.pixelSize: 11
                            elide: Text.ElideRight
                        }
                        MouseArea { anchors.fill: parent; onClicked: root.selected = tile.modelData }
                    }
                }
                RowLayout {
                    visible: root.remote
                    ActionButton { label: strings.t("previous"); enabled: !busy && page > 1; onClicked: root.search(page - 1) }
                    Text { textFormat: Text.PlainText; text: strings.t("page").arg(page); color: Commons.Color.muted }
                    ActionButton { label: strings.t("next"); enabled: !busy && more; onClicked: root.search(page + 1) }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        Layout.fillWidth: true
                        textFormat: Text.PlainText
                        text: selected ? selected.title : strings.t("select")
                        color: Commons.Color.foreground
                        elide: Text.ElideRight
                    }
                    ActionButton { label: strings.t("stop"); enabled: !busy; onClicked: root.perform("stop", "") }
                    ActionButton { label: strings.t("download"); enabled: !busy && selected !== null; onClicked: root.perform("download", selected.id) }
                    ActionButton { label: strings.t("apply"); active: true; enabled: !busy && selected !== null && selected.installed; onClicked: root.perform("set", selected.id) }
                }
                RowLayout {
                    visible: status !== "" || busy
                    Layout.fillWidth: true
                    BusyIndicator { running: busy; visible: busy; implicitWidth: 24; implicitHeight: 24 }
                    Text {
                        Layout.fillWidth: true
                        textFormat: Text.PlainText
                        text: status
                        color: failed ? Commons.Color.urgent : Commons.Color.foreground
                        wrapMode: Text.WordWrap
                        maximumLineCount: 4
                        elide: Text.ElideRight
                        font.pixelSize: 12
                    }
                    ActionButton { label: strings.t("cancel"); visible: busy; onClicked: { action.running = false; listing.running = false } }
                }
            }
            Rectangle {
                visible: root.qrPath !== ""
                anchors.centerIn: parent
                width: 390
                height: 460
                radius: 10
                color: Commons.Color.background
                border.color: Commons.Color.accent
                Image {
                    anchors { top: parent.top; horizontalCenter: parent.horizontalCenter; topMargin: 24 }
                    width: 320; height: 320
                    source: root.qrPath
                    cache: false
                    fillMode: Image.PreserveAspectFit
                }
                Text {
                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 24; bottomMargin: 65 }
                    textFormat: Text.PlainText
                    text: strings.t("scan")
                    color: Commons.Color.foreground
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.WordWrap
                }
                ActionButton { anchors { bottom: parent.bottom; horizontalCenter: parent.horizontalCenter; bottomMargin: 18 } label: strings.t("cancel"); onClicked: action.running = false }
            }
        }
    }
}
