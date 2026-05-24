import './App.css';

function App() {
  return (
    <div className="App">
      <nav className="navbar">
        <div className="navbar-brand">
          <span className="brand-title">GreengapFinder</span>
          <span className="brand-subtitle">서울 시민들을 위한 녹지 플랫폼</span>
        </div>
        <div className="navbar-menu">
          <button className="nav-btn">button1</button>
          <button className="nav-btn">button2</button>
          <button className="nav-btn">button3</button>
          <button className="nav-btn">button4</button>
        </div>
      </nav>

      <main className="main-content">
        <div className="map-embed">
          <span>지도 embed</span>
        </div>
      </main>
    </div>
  );
}

export default App;
