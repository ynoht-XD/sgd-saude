// agenda.js - versão com setas separadas para mês e semana + agendamentos múltiplos e horários até 22:00

document.addEventListener('DOMContentLoaded', () => {
  const semanaHeader = document.getElementById('semanaHeader');
  const gradeHorarios = document.getElementById('gradeHorarios');
  const modal = document.getElementById('modalAgendamento');
  const fecharModal = document.getElementById('fecharModal');
  const salvarAgendamento = document.getElementById('salvarAgendamento');

  const btnHoje = document.getElementById('btnHoje');
  const mesAnterior = document.getElementById('mesAnterior');
  const mesProximo = document.getElementById('mesProximo');
  const semanaAnterior = document.getElementById('semanaAnterior');
  const semanaProximo = document.getElementById('semanaProximo');
  const mesAno = document.getElementById('mesAno');

  let dataBase = new Date();
  const agendamentos = {}; // { 'dia|hora:min': ["Paciente"] }

  const diasSemana = ['DOM.', 'SEG.', 'TER.', 'QUA.', 'QUI.', 'SEX.', 'SÁB.'];

  function atualizarAgenda() {
    semanaHeader.innerHTML = '';
    gradeHorarios.innerHTML = '';

    const inicioSemana = new Date(dataBase);
    inicioSemana.setDate(dataBase.getDate() - dataBase.getDay());

    const datasSemana = [];
    for (let i = 0; i < 7; i++) {
      const data = new Date(inicioSemana);
      data.setDate(inicioSemana.getDate() + i);
      datasSemana.push(data);

      const div = document.createElement('div');
      div.classList.add('cabecalho-dia');
      div.innerHTML = `
        <div>${diasSemana[i]}</div>
        <div>${data.getDate().toString().padStart(2, '0')}/${(data.getMonth() + 1).toString().padStart(2, '0')}</div>
      `;
      semanaHeader.appendChild(div);
    }

    mesAno.textContent = dataBase.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' });

    for (let h = 7; h <= 22; h++) {
      ['00', '30'].forEach(min => {
        const horaStr = `${h.toString().padStart(2, '0')}:${min}`;

        datasSemana.forEach((data, colIndex) => {
          const dia = data.toISOString().split('T')[0];
          const chave = `${dia}|${horaStr}`;

          const celula = document.createElement('div');
          celula.classList.add('celula');
          celula.dataset.horario = horaStr;
          celula.dataset.coluna = colIndex;
          celula.dataset.dia = dia;

          celula.addEventListener('click', () => abrirModal(horaStr, dia));

          if (agendamentos[chave]) {
            agendamentos[chave].forEach(nome => {
              const bloco = document.createElement('div');
              bloco.classList.add('agendamento');
              bloco.textContent = nome;
              celula.appendChild(bloco);
            });
          }

          gradeHorarios.appendChild(celula);
        });
      });
    }
  }

  function abrirModal(horario, dia) {
    modal.style.display = 'block';
    modal.dataset.horario = horario;
    modal.dataset.dia = dia;
  }

  fecharModal.onclick = () => {
    modal.style.display = 'none';
  };

  window.onclick = (event) => {
    if (event.target === modal) {
      modal.style.display = 'none';
    }
  };

  salvarAgendamento.onclick = () => {
    const paciente = document.getElementById('paciente').value;
    const profissional = document.getElementById('profissional').value;
    const tipo = document.querySelector('input[name="tipo"]:checked').value;
    const qtdSessoes = document.getElementById('quantidadeSessoes').value;
    const recorrenteIndefinido = document.getElementById('pacienteRecorrente').checked;

    const horario = modal.dataset.horario;
    const dia = modal.dataset.dia;
    const chave = `${dia}|${horario}`;

    if (!agendamentos[chave]) agendamentos[chave] = [];
    agendamentos[chave].push(paciente);

    modal.style.display = 'none';
    atualizarAgenda();
  };

  btnHoje.onclick = () => {
    dataBase = new Date();
    atualizarAgenda();
  };

  mesAnterior.onclick = () => {
    dataBase.setMonth(dataBase.getMonth() - 1);
    atualizarAgenda();
  };

  mesProximo.onclick = () => {
    dataBase.setMonth(dataBase.getMonth() + 1);
    atualizarAgenda();
  };

  semanaAnterior.onclick = () => {
    dataBase.setDate(dataBase.getDate() - 7);
    atualizarAgenda();
  };

  semanaProximo.onclick = () => {
    dataBase.setDate(dataBase.getDate() + 7);
    atualizarAgenda();
  };

  atualizarAgenda();
});