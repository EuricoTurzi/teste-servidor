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

# Endpoint para receber dados
@app.route('/receive_data', methods=['POST'])
def receive_data():
    data = request.json  # Espera dados JSON
    # Validação: verificar se há exatamente 6 células vizinhas
    neighbor_cells = data.get('neighbor_cells', [])
    if len(neighbor_cells) != 6:
        return jsonify({'status': 'error', 'message': 'Exatamente 6 células vizinhas são necessárias'}), 400
    
    # Criando a entrada principal de dados do dispositivo
    device_data = DeviceData(
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
    db.session.add(device_data)
    db.session.flush()  # Garante que `device_data.id` é gerado antes de salvar células vizinhas

    # Adiciona as 6 células vizinhas
    for neighbor in neighbor_cells:
        neighbor_cell = NeighborCell(
            device_data_id=device_data.id,
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
    <head><meta charset="UTF-8"><title>Data Viewer</title></head>
    <body>
        <h2>Última Atualização</h2>
        <div id="data">Aguardando dados...</div>
        
        <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
        <script>
            var socket = io();
            socket.on('new_data', function(data) {
                document.getElementById("data").innerText = "Dados Recebidos: " + JSON.stringify(data);
            });
        </script>
    </body>
    </html>
    """

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Cria as tabelas no banco de dados
    port = int(os.environ.get("PORT", 8080))
<<<<<<< HEAD
    socketio.run(app, host='0.0.0.0', port=port)  # Parâmetro server='eventlet' foi removido
=======
    socketio.run(app, host='0.0.0.0', port=port, server='eventlet')
>>>>>>> 02508e92eebb42aabb2fd60d4156b31e78a26302
