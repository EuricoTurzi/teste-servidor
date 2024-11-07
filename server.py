import eventlet
eventlet.monkey_patch()  # Deve ser chamado antes de qualquer outro import

from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from datetime import datetime
import os
import eventlet
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

        <script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
        <script>
            var map = L.map('map').setView([-23.636415, -46.512757], 12);

            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                maxZoom: 19,
                attribution: '© OpenStreetMap'
            }).addTo(map);

            // Armazena marcadores para múltiplos dispositivos
            var markers = {};

            function updateData() {
                fetch('/latest_data')
                    .then(response => response.json())
                    .then(devices => {
                        // Limpa a tabela
                        const dataBody = document.getElementById("data-body");
                        dataBody.innerHTML = '';

                        // Atualiza cada dispositivo no mapa e na tabela
                        devices.forEach(device => {
                            // Atualiza ou cria um marcador no mapa
                            var lat = device.latitude;
                            var lon = device.longitude;
                            if (markers[device.device_id]) {
                                markers[device.device_id].setLatLng([lat, lon]);
                            } else {
                                markers[device.device_id] = L.marker([lat, lon]).addTo(map)
                                    .bindPopup("<b>ID do Dispositivo:</b> " + device.device_id);
                            }

                            // Adiciona uma linha na tabela para cada dispositivo
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

            setInterval(updateData, 5000);  // Atualiza a cada 5 segundos
        </script>
    </body>
    </html>
    """

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Cria as tabelas no banco de dados
    port = int(os.environ.get("PORT", 8080))
    socketio.run(app, host='0.0.0.0', port=port)  # Parâmetro server='eventlet' foi removido
