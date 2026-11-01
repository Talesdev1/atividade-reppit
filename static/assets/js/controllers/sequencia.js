angular.module('deciframeApp').controller('SequenciaController', function($http, $window, ngProgressFactory, $anchorScroll, $location, GENEROS) {
  var COR = '#2E1C74';
  var MAX_ACORDES = 16;

  var vm = this;
  vm.sequenciasFamosas = [];
  vm.minhaSequencia = {};
  vm.isSearching = false;
  vm.showSearchResultsCount = false;
  vm.esfigeSpeech = "";
  vm.musics = [];
  vm.generos = GENEROS;
  vm.meuGenero = "";
  vm.progressbar = ngProgressFactory.createInstance();

  // formulário de cadastro (catálogo aberto e anônimo)
  vm.novaSequencia = { acordes: [] };
  vm.acordeInput = "";
  vm.cadastrando = false;
  vm.mensagemCadastro = "";

  // a API responde json.dumps(...) como text/html; aceita string ou objeto.
  var parseResposta = function(data) {
    if (typeof data === 'string') {
      try {
        return JSON.parse(data);
      } catch (e) {
        return data;
      }
    }
    return data;
  };

  var toViewModel = function(sequencia) {
    return {
      id: sequencia.id,
      origem: sequencia.origem,
      acordes: (sequencia.acordes || []).map(function(acorde) {
        return { acorde: acorde, cor: COR };
      })
    };
  };

  vm.carregarSequencias = function() {
    $http.get('sequencias')
      .success(function(data) {
        vm.sequenciasFamosas = parseResposta(data).map(toViewModel);
      })
      .error(function() {
        vm.esfigeSpeech = "Ops! Não consegui carregar o catálogo de sequências.";
      });
  };

  vm.temAcorde = function(acordeon) {
    var acordes = vm.minhaSequencia && vm.minhaSequencia.acordes;
    if (!acordes || !acordeon) {
      return false;
    }
    var alvo = acordeon.acorde || acordeon;
    return acordes.some(function(item) { return item.acorde === alvo; });
  };

  var createChordsString = function(chords) {
    var str = "";
    for (var i = 0; i < chords.length; i++) {
      str = str.concat(chords[i].acorde, ',');
    }
    return str.substring(0, str.length-1);
  }

  vm.adicionarAcorde = function() {
    var acorde = (vm.acordeInput || '').trim();
    if (!acorde) {
      return;
    }
    if (vm.novaSequencia.acordes.length >= MAX_ACORDES) {
      vm.mensagemCadastro = "Uma sequência aceita no máximo " + MAX_ACORDES + " acordes.";
      return;
    }
    vm.novaSequencia.acordes.push({ 'acorde': acorde, 'cor': COR });
    vm.acordeInput = "";
    vm.mensagemCadastro = "";
  };

  vm.adicionarAcordeTecla = function(evento) {
    if (evento && evento.keyCode === 13) {
      evento.preventDefault();
      vm.adicionarAcorde();
    }
  };

  vm.removerAcorde = function(indice) {
    vm.novaSequencia.acordes.splice(indice, 1);
  };

  vm.cadastrarSequencia = function() {
    var acordes = vm.novaSequencia.acordes.map(function(item) { return item.acorde; });
    if (acordes.length < 2) {
      vm.mensagemCadastro = "Adicione ao menos 2 acordes para cadastrar.";
      return;
    }
    vm.cadastrando = true;
    vm.mensagemCadastro = "";

    $http.post('sequencias', { 'acordes': acordes })
      .success(function(data) {
        var sequencia = toViewModel(parseResposta(data));
        vm.cadastrando = false;
        vm.novaSequencia = { acordes: [] };
        vm.carregarSequencias();
        vm.pesquisarPorSequencia(sequencia);
      })
      .error(function(data, status) {
        vm.cadastrando = false;
        var corpo = parseResposta(data);
        if (status === 409) {
          vm.mensagemCadastro = "Essa sequência já está no catálogo.";
        } else if (corpo && corpo.erro) {
          vm.mensagemCadastro = corpo.erro;
        } else {
          vm.mensagemCadastro = "Ops! Não consegui cadastrar a sequência.";
        }
      });
  };

  vm.pesquisarPorSequencia = function(sequencia) {
    if (sequencia) {
      vm.minhaSequencia = sequencia;
    }
    if (!vm.minhaSequencia.acordes || !vm.minhaSequencia.acordes.length) {
      return;
    }
    vm.progressbar.start();
    vm.esfigeSpeech = "Procurando músicas com base na sequencia...";
    vm.isSearching = true;
    vm.musics = [];

    // $http serializa e codifica os parâmetros: acordes com '#', '+' ou '%'
    // (ex.: C#, A#5+) não podem ser concatenados crus na URL.
    var params = { sequencia: createChordsString(vm.minhaSequencia.acordes) };
    if (vm.meuGenero !== "" && vm.meuGenero !== null) {
      params.generos = vm.meuGenero;
    }
    $http.get('similares', { params: params })
      .success(function(data) {
        vm.progressbar.complete();
        vm.esfigeSpeech = "Encontrei essas músicas";
        vm.isSearching = false;
        vm.showSearchResultsCount = true;
        vm.musics = parseResposta(data);
      })
      .error(function(data) {
        vm.esfigeSpeech = "Ops! Algo errado.";
        vm.isSearching = false;
        vm.showSearchResultsCount = false;
      });
  }

  vm.limparPesquisa = function() {
    vm.minhaSequencia = {};
    vm.musics = [];
  }

  vm.goToLirics = function(music) {
    $window.open(music.url);
  };

  vm.goToResults = function() {
    vm.showSearchResultsCount = false;
    $("body").animate({scrollTop: $("#results").offset().top}, "slow");
  };

  vm.carregarSequencias();
});
