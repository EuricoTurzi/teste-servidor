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

    # Verifica se já existe um registro para este device_id e, em caso afirmativo, remove as células vizinhas associadas
    existing_device = DeviceData.query.filter_by(device_id=data['device_id']).first()
    if existing_device:
        # Exclui as células vizinhas associadas ao dispositivo
        NeighborCell.query.filter_by(device_data_id=existing_device.id).delete()
        db.session.commit()

        # Atualiza os dados do dispositivo
        existing_device.sw_version = data['sw_version']
        existing_device.model = data['model']
        existing_device.cell_id = data['cell_id']
        existing_device.mcc = data['mcc']
        existing_device.mnc = data['mnc']
        existing_device.rx_lvl = data['rx_lvl']
        existing_device.lac = data['lac']
        existing_device.tm_adv = data['tm_adv']
        existing_device.backup_voltage = data['backup_voltage']
        existing_device.online_status = data['online_status']
        existing_device.message_number = data['message_number']
        existing_device.mode = data['mode']
        existing_device.col_net_rf_ch = data['col_net_rf_ch']
        existing_device.gps_date = data['gps_date']
        existing_device.gps_time = data['gps_time']
        existing_device.latitude = data['latitude']
        existing_device.longitude = data['longitude']
        existing_device.speed = data['speed']
        existing_device.course = data['course']
        existing_device.satt = data['satt']
        existing_device.gps_fix = data['gps_fix']
        existing_device.temperature = data['temperature']
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
        db.session.flush()  # Garante que `existing_device.id` é gerado

    # Adiciona as 6 novas células vizinhas
    for neighbor in neighbor_cells:
        neighbor_cell = NeighborCell(
            device_data_id=existing_device.id,
            cell_id=neighbor['cell_id'],
            mcc=neighbor['mcc'],
            mnc=neighbor['mnc'],
            lac=neighbor['lac'],
            rx_lvl=neighbor['rx_lvl'],
            tm_adv=neighbor['tm_adv']
        )
        db.session.add(neighbor_cell)

    db.session.commit()
    
    # Emite a atualização para os clientes conectados
    socketio.emit('new_data', data)
    
    return jsonify({'status': 'success'})

# Interface principal para visualização em tempo real
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
            <tr>
                <th>Campo</th>
                <th>Valor</th>
            </tr>
            <tr><td>ID do Dispositivo</td><td id="device_id">Aguardando dados...</td></tr>
            <tr><td>Latitude</td><td id="latitude">Aguardando dados...</td></tr>
            <tr><td>Longitude</td><td id="longitude">Aguardando dados...</td></tr>
            <tr><td>Velocidade</td><td id="speed">Aguardando dados...</td></tr>
            <tr><td>Temperatura</td><td id="temperature">Aguardando dados...</td></tr>
            <!-- Adicione outras linhas conforme necessário -->
        </table>

        <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
        <script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
        <script>
            // Inicializa o mapa centrado em uma localização padrão
            var map = L.map('map').setView([-23.636415, -46.512757], 12); // Coordenadas padrão

            // Adiciona o tile layer do OpenStreetMap
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                maxZoom: 19,
                attribution: '© OpenStreetMap'
            }).addTo(map);

            // Variável para o marcador (para ser atualizado em tempo real)
            var marker = null;

            // Conecta ao servidor Socket.IO
            var socket = io();

            // Quando novos dados forem recebidos
            socket.on('new_data', function(data) {
                // Atualiza a tabela de dados
                document.getElementById("device_id").innerText = data.device_id;
                document.getElementById("latitude").innerText = data.latitude;
                document.getElementById("longitude").innerText = data.longitude;
                document.getElementById("speed").innerText = data.speed;
                document.getElementById("temperature").innerText = data.temperature;

                // Atualiza o marcador no mapa
                var lat = data.latitude;
                var lon = data.longitude;
                if (marker) {
                    // Se o marcador já existe, move-o para a nova posição
                    marker.setLatLng([lat, lon]);
                } else {
                    // Se não existe, cria um novo marcador
                    marker = L.marker([lat, lon]).addTo(map);
                }

                // Atualiza a visão do mapa para a nova posição do dispositivo
                map.setView([lat, lon], 15);
                
                // Pop-up com informações ao clicar no marcador
                marker.bindPopup("<b>ID do Dispositivo:</b> " + data.device_id + "<br><b>Velocidade:</b> " + data.speed + " km/h<br><b>Temperatura:</b> " + data.temperature + " °C").openPopup();
            });
        </script>
    </body>
    </html>
    """

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Cria as tabelas no banco de dados
    port = int(os.environ.get("PORT", 8080))
    socketio.run(app, host='0.0.0.0', port=port)  # Parâmetro server='eventlet' foi removido
