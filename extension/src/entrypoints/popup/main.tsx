import React from "react";
import ReactDOM from "react-dom/client";
import { Popup } from "./Popup";
import "./style.css";

const root = document.getElementById("root");
if (!root) throw new Error("#root missing");

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <Popup />
  </React.StrictMode>,
);