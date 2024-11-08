import eventlet
eventlet.monkey_patch()  # Deve ser chamado antes de qualquer outro import

from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from datetime import datetime
import os
import eventlet
import socket
eventlet.monkey_patch()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
socketio = SocketIO(app)

# Modelos do banco de dados
class DeviceData(db.Model):
    __tablename__ = 'device_data'
    id = db.Column(db.Integer, primary_key=True)
    device_id = db.Column(db.String(20))
    sw_version = db.Column(db.String(10))
    model = db.Column(db.String(10))
    cell_id = db.Column(db.String(10))
    mcc = db.Column(db.String(5))
    mnc = db.Column(db.String(5))
    rx_lvl = db.Column(db.String(5))
    lac = db.Column(db.String(10))
    tm_adv = db.Column(db.String(5))
    backup_voltage = db.Column(db.Float)
    online_status = db.Column(db.Boolean)
    message_number = db.Column(db.Integer)
    mode = db.Column(db.String(5))
    col_net_rf_ch = db.Column(db.String(5))
    gps_date = db.Column(db.Date)
    gps_time = db.Column(db.Time)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    speed = db.Column(db.Float)
    course = db.Column(db.Float)
    satt = db.Column(db.Integer)
    gps_fix = db.Column(db.Boolean)
    temperature = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    neighbor_cells = db.relationship('NeighborCell', backref='device_data', cascade="all, delete-orphan")

class NeighborCell(db.Model):
    __tablename__ = 'neighbor_cells'
    id = db.Column(db.Integer, primary_key=True)
    device_data_id = db.Column(db.Integer, db.ForeignKey('device_data.id'))
    cell_id = db.Column(db.String(10))
    mcc = db.Column(db.String(5))
    mnc = db.Column(db.String(5))
    lac = db.Column(db.String(10))
    rx_lvl = db.Column(db.String(5))
    tm_adv = db.Column(db.String(5))

@app.route('/receive_data', methods=['POST'])
def receive_data():
    data = request.json  # Espera dados JSON

    # Validação: verificar se há exatamente 6 células vizinhas
    neighbor_cells = data.get('neighbor_cells', [])
    if len(neighbor_cells) != 6:
        return jsonify({'status': 'error', 'message': 'Exatamente 6 células vizinhas são necessárias'}), 400

    # Verifica se já existe um registro para este device_id
    existing_device = DeviceData.query.filter_by(device_id=data['device_id']).first()

    # Se o dispositivo já existe, atualize o registro e exclua as células vizinhas antigas
    if existing_device:
        # Exclui as células vizinhas associadas ao dispositivo
        NeighborCell.query.filter_by(device_data_id=existing_device.id).delete()
        db.session.commit()  # Confirma a exclusão das células vizinhas

        # Atualiza os dados do dispositivo
        for field in [
            'sw_version', 'model', 'cell_id', 'mcc', 'mnc', 'rx_lvl', 'lac', 'tm_adv',
            'backup_voltage', 'online_status', 'message_number', 'mode', 'col_net_rf_ch',
            'gps_date', 'gps_time', 'latitude', 'longitude', 'speed', 'course', 'satt',
            'gps_fix', 'temperature'
        ]:
            setattr(existing_device, field, data.get(field))
    else:
        # Se não existe, cria um novo registro para o dispositivo
        existing_device = DeviceData(
            device_id=data['device_id'],
            sw_version=data['sw_version'],
            model=data['model'],
            cell_id=data['cell_id'],
            mcc=data['mcc'],
            mnc=data['mnc'],
            rx_lvl=data['rx_lvl'],
            lac=data['lac'],
            tm_adv=data['tm_adv'],
            backup_voltage=data['backup_voltage'],
            online_status=data['online_status'],
            message_number=data['message_number'],
            mode=data['mode'],
            col_net_rf_ch=data['col_net_rf_ch'],
            gps_date=data['gps_date'],
            gps_time=data['gps_time'],
            latitude=data['latitude'],
            longitude=data['longitude'],
            speed=data['speed'],
            course=data['course'],
            satt=data['satt'],
            gps_fix=data['gps_fix'],
            temperature=data['temperature']
        )
        db.session.add(existing_device)
        db.session.flush()  # Garante que `existing_device.id` é gerado antes de adicionar células vizinhas

    # Adiciona as 6 novas células vizinhas
    for neighbor in neighbor_cells:
        neighbor_cell = NeighborCell(
            device_data_id=existing_device.id,
            cell_id=neighbor.get('cell_id'),
            mcc=neighbor.get('mcc'),
            mnc=neighbor.get('mnc'),
            lac=neighbor.get('lac'),
            rx_lvl=neighbor.get('rx_lvl'),
            tm_adv=neighbor.get('tm_adv')
        )
        db.session.add(neighbor_cell)

    db.session.commit()

    # Emite a atualização para os clientes conectados
    socketio.emit('new_data', data)

    return jsonify({'status': 'success'})

@app.route('/latest_data', methods=['GET'])
def get_latest_data():
    # Obtém o dado mais recente de cada dispositivo, ordenado por device_id para garantir que temos apenas os dispositivos únicos
    devices = DeviceData.query.order_by(DeviceData.device_id, DeviceData.created_at.desc()).all()
    
    if not devices:
        return jsonify({"status": "error", "message": "Nenhum dado disponível"}), 404

    data = []
    # Itera sobre os dispositivos, garantindo que apenas o último registro de cada dispositivo seja adicionado
    seen_devices = set()
    for device in devices:
        if device.device_id in seen_devices:
            continue  # Pula dispositivos que já foram adicionados
        seen_devices.add(device.device_id)
        
        device_info = {
            "device_id": device.device_id,
            "backup_voltage": device.backup_voltage,
            "online_status": device.online_status,
            "mode": device.mode,
            "gps_date": device.gps_date.isoformat(),
            "gps_time": device.gps_time.strftime("%H:%M:%S") if device.gps_time else "N/A",
            "latitude": device.latitude,
            "longitude": device.longitude,
            "gps_fix": device.gps_fix,
        }
        data.append(device_info)

    return jsonify(data), 200

@app.route('/send_command', methods=['POST'])
def send_command():
    data = request.json
    device_id = data.get("device_id")
    command_type = data.get("command_type")

    # Validação dos parâmetros recebidos
    if not device_id or not command_type:
        return jsonify({"status": "error", "message": "device_id e command_type são obrigatórios"}), 400

    # Formatação do comando com base no tipo solicitado
    if command_type == "ReqICCID":
        command = f"AT^ST410CMD;{device_id};02;ReqICCID"
    elif command_type == "StartEmg":
        command = f"AT^ST410CMD;{device_id};02;StartEmg"
    elif command_type == "StopEmg":
        command = f"AT^ST410CMD;{device_id};02;StopEmg"
    else:
        return jsonify({"status": "error", "message": "Comando inválido"}), 400

    # Envia o comando para o servidor TCP na AWS
    try:
        # Conecta ao servidor TCP na AWS
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect(("IP_DO_SERVIDOR_AWS", 8080))  # Substitua pelo IP correto da AWS
            sock.sendall(command.encode('utf-8'))
            response = sock.recv(1024).decode('utf-8')  # Recebe a resposta do servidor TCP

        return jsonify({"status": "success", "command_sent": command, "response": response}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": f"Falha ao enviar comando: {str(e)}"}), 500

@app.route('/')
def index():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Data Viewer</title>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.7.1/dist/leaflet.css" />
        <style>
            #map { height: 400px; width: 100%; }
            #data-table { margin-top: 20px; border-collapse: collapse; width: 100%; }
            #data-table th, #data-table td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            #data-table th { background-color: #f2f2f2; }
            #command-form { margin-top: 20px; }
        </style>
    </head>
    <body>
        <h2>Última Atualização</h2>
        <div id="map"></div>
        <table id="data-table">
            <thead>
                <tr>
                    <th>ID do Dispositivo</th>
                    <th>Backup Voltage</th>
                    <th>Status Online</th>
                    <th>Modo</th>
                    <th>Data GPS</th>
                    <th>Hora GPS</th>
                    <th>Latitude</th>
                    <th>Longitude</th>
                    <th>GPS Fix</th>
                </tr>
            </thead>
            <tbody id="data-body">
                <!-- Dados dos dispositivos serão inseridos aqui -->
            </tbody>
        </table>

        <!-- Formulário para envio de comando -->
        <div id="command-form">
            <h3>Enviar Comando</h3>
            <label for="device-id">ID do Dispositivo:</label>
            <input type="text" id="device-id" placeholder="Digite o ID do dispositivo" required>
            <label for="command-type">Tipo de Comando:</label>
            <select id="command-type" required>
                <option value="">Selecione o Comando</option>
                <option value="ReqICCID">ReqICCID</option>
                <option value="StartEmg">StartEmg</option>
                <option value="StopEmg">StopEmg</option>
            </select>
            <button onclick="sendCommand()">Enviar Comando</button>
            <p id="command-response"></p>
        </div>

        <script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
        <script>
            var map = L.map('map').setView([-23.636415, -46.512757], 12);

            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                maxZoom: 19,
                attribution: '© OpenStreetMap'
            }).addTo(map);

            var markers = {};

            function updateData() {
                fetch('/latest_data')
                    .then(response => response.json())
                    .then(devices => {
                        const dataBody = document.getElementById("data-body");
                        dataBody.innerHTML = '';

                        devices.forEach(device => {
                            var lat = device.latitude;
                            var lon = device.longitude;
                            if (markers[device.device_id]) {
                                markers[device.device_id].setLatLng([lat, lon]);
                            } else {
                                markers[device.device_id] = L.marker([lat, lon]).addTo(map)
                                    .bindPopup("<b>ID do Dispositivo:</b> " + device.device_id);
                            }

                            const row = document.createElement('tr');
                            row.innerHTML = `
                                <td>${device.device_id}</td>
                                <td>${device.backup_voltage}</td>
                                <td>${device.online_status ? 'Sim' : 'Não'}</td>
                                <td>${device.mode}</td>
                                <td>${device.gps_date}</td>
                                <td>${device.gps_time}</td>
                                <td>${device.latitude}</td>
                                <td>${device.longitude}</td>
                                <td>${device.gps_fix ? 'Sim' : 'Não'}</td>
                            `;
                            dataBody.appendChild(row);
                        });
                    })
                    .catch(error => console.error('Erro ao obter dados:', error));
            }

            setInterval(updateData, 5000);

            function sendCommand() {
                const deviceId = document.getElementById("device-id").value;
                const commandType = document.getElementById("command-type").value;
                const responseText = document.getElementById("command-response");

                if (!deviceId || !commandType) {
                    responseText.textContent = "Por favor, preencha todos os campos.";
                    return;
                }

                fetch('/send_command', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ device_id: deviceId, command_type: commandType })
                })
                .then(response => response.json())
                .then(data => {
                    if (data.status === "success") {
                        responseText.textContent = "Comando enviado com sucesso!";
                    } else {
                        responseText.textContent = `Erro: ${data.message}`;
                    }
                })
                .catch(error => {
                    console.error('Erro ao enviar comando:', error);
                    responseText.textContent = "Erro ao enviar comando.";
                });
            }
        </script>
    </body>
    </html>
    """

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Cria as tabelas no banco de dados
    port = int(os.environ.get("PORT", 8080))
    socketio.run(app, host='0.0.0.0', port=port)  # Parâmetro server='eventlet' foi removido
