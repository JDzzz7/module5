import datetime
from pathlib import Path
import pandas as pd
import pytest
from unittest.mock import Mock, patch, PropertyMock
from decimal import Decimal
from tempfile import TemporaryDirectory
from app.calculator import Calculator
from app.calculator_repl import calculator_repl
from app.calculation import Calculation
from app.calculator_config import CalculatorConfig
from app.exceptions import OperationError, ValidationError
from app.history import LoggingObserver, AutoSaveObserver
from app.operations import OperationFactory

# Fixture to initialize Calculator with a temporary directory for file paths
@pytest.fixture
def calculator():
    with TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        config = CalculatorConfig(base_dir=temp_path)

        # Patch properties to use the temporary directory paths
        with patch.object(CalculatorConfig, 'log_dir', new_callable=PropertyMock) as mock_log_dir, \
             patch.object(CalculatorConfig, 'log_file', new_callable=PropertyMock) as mock_log_file, \
             patch.object(CalculatorConfig, 'history_dir', new_callable=PropertyMock) as mock_history_dir, \
             patch.object(CalculatorConfig, 'history_file', new_callable=PropertyMock) as mock_history_file:
            
            # Set return values to use paths within the temporary directory
            mock_log_dir.return_value = temp_path / "logs"
            mock_log_file.return_value = temp_path / "logs/calculator.log"
            mock_history_dir.return_value = temp_path / "history"
            mock_history_file.return_value = temp_path / "history/calculator_history.csv"
            
            # Return an instance of Calculator with the mocked config
            yield Calculator(config=config)

# Test Calculator Initialization

def test_calculator_initialization(calculator):
    assert calculator.history == []
    assert calculator.undo_stack == []
    assert calculator.redo_stack == []
    assert calculator.operation_strategy is None

# Test Logging Setup

@patch('app.calculator.logging.info')
def test_logging_setup(logging_info_mock):
    with patch.object(CalculatorConfig, 'log_dir', new_callable=PropertyMock) as mock_log_dir, \
         patch.object(CalculatorConfig, 'log_file', new_callable=PropertyMock) as mock_log_file:
        mock_log_dir.return_value = Path('/tmp/logs')
        mock_log_file.return_value = Path('/tmp/logs/calculator.log')
        
        # Instantiate calculator to trigger logging
        calculator = Calculator(CalculatorConfig())
        logging_info_mock.assert_any_call("Calculator initialized with configuration")

# Test Adding and Removing Observers

def test_add_observer(calculator):
    observer = LoggingObserver()
    calculator.add_observer(observer)
    assert observer in calculator.observers

def test_remove_observer(calculator):
    observer = LoggingObserver()
    calculator.add_observer(observer)
    calculator.remove_observer(observer)
    assert observer not in calculator.observers

# Test Setting Operations

def test_set_operation(calculator):
    operation = OperationFactory.create_operation('add')
    calculator.set_operation(operation)
    assert calculator.operation_strategy == operation

# Test Performing Operations

def test_perform_operation_addition(calculator):
    operation = OperationFactory.create_operation('add')
    calculator.set_operation(operation)
    result = calculator.perform_operation(2, 3)
    assert result == Decimal('5')

def test_perform_operation_validation_error(calculator):
    calculator.set_operation(OperationFactory.create_operation('add'))
    with pytest.raises(ValidationError):
        calculator.perform_operation('invalid', 3)

def test_perform_operation_operation_error(calculator):
    with pytest.raises(OperationError, match="No operation set"):
        calculator.perform_operation(2, 3)

# Test Undo/Redo Functionality

def test_undo(calculator):
    operation = OperationFactory.create_operation('add')
    calculator.set_operation(operation)
    calculator.perform_operation(2, 3)
    calculator.undo()
    assert calculator.history == []

def test_redo(calculator):
    operation = OperationFactory.create_operation('add')
    calculator.set_operation(operation)
    calculator.perform_operation(2, 3)
    calculator.undo()
    calculator.redo()
    assert len(calculator.history) == 1

# Test History Management

@patch('app.calculator.pd.DataFrame.to_csv')
def test_save_history(mock_to_csv, calculator):
    operation = OperationFactory.create_operation('add')
    calculator.set_operation(operation)
    calculator.perform_operation(2, 3)
    calculator.save_history()
    mock_to_csv.assert_called_once()

@patch('app.calculator.pd.read_csv')
@patch('app.calculator.Path.exists', return_value=True)
def test_load_history(mock_exists, mock_read_csv, calculator):
    # Mock CSV data to match the expected format in from_dict
    mock_read_csv.return_value = pd.DataFrame({
        'operation': ['Addition'],
        'operand1': ['2'],
        'operand2': ['3'],
        'result': ['5'],
        'timestamp': [datetime.datetime.now().isoformat()]
    })
    
    # Test the load_history functionality
    try:
        calculator.load_history()
        # Verify history length after loading
        assert len(calculator.history) == 1
        # Verify the loaded values
        assert calculator.history[0].operation == "Addition"
        assert calculator.history[0].operand1 == Decimal("2")
        assert calculator.history[0].operand2 == Decimal("3")
        assert calculator.history[0].result == Decimal("5")
    except OperationError:
        pytest.fail("Loading history failed due to OperationError")
        
            
# Test Clearing History

def test_clear_history(calculator):
    operation = OperationFactory.create_operation('add')
    calculator.set_operation(operation)
    calculator.perform_operation(2, 3)
    calculator.clear_history()
    assert calculator.history == []
    assert calculator.undo_stack == []
    assert calculator.redo_stack == []

# Test REPL Commands (using patches for input/output handling)

@patch('builtins.input', side_effect=['exit'])
@patch('builtins.print')
def test_calculator_repl_exit(mock_print, mock_input):
    with patch('app.calculator.Calculator.save_history') as mock_save_history:
        calculator_repl()
        mock_save_history.assert_called_once()
        mock_print.assert_any_call("History saved successfully.")
        mock_print.assert_any_call("Goodbye!")

@patch('builtins.input', side_effect=['help', 'exit'])
@patch('builtins.print')
def test_calculator_repl_help(mock_print, mock_input):
    calculator_repl()
    mock_print.assert_any_call("\nAvailable commands:")

@patch('builtins.input', side_effect=['add', '2', '3', 'exit'])
@patch('builtins.print')
def test_calculator_repl_addition(mock_print, mock_input):
    calculator_repl()
    mock_print.assert_any_call("\nResult: 5")

def test_initialization_load_history_exception():
    config = Mock(spec=CalculatorConfig)
    config.log_dir = Path("/tmp/logs")
    config.log_file = Path("/tmp/logs/calculator.log")
    config.history_dir = Path("/tmp/history")
    config.history_file = Path("/tmp/history/history.csv")
    config.validate = Mock()

    with patch.object(Calculator, "load_history", side_effect=Exception("load failed")), \
         patch.object(Calculator, "_setup_logging"), \
         patch.object(Calculator, "_setup_directories"), \
         patch("app.calculator.os.makedirs"), \
         patch("app.calculator.logging.warning") as mock_warning:

        Calculator(config=config)

        mock_warning.assert_called_once_with(
            "Could not load existing history: load failed"
        )


def test_setup_logging_exception(calculator):
    with patch("app.calculator.os.makedirs",
               side_effect=OSError("logging failed")), \
         patch("builtins.print") as mock_print:

        with pytest.raises(OSError, match="logging failed"):
            calculator._setup_logging()

        mock_print.assert_called_once_with(
            "Error setting up logging: logging failed"
        )


def test_notify_observers(calculator):
    observer1 = Mock()
    observer2 = Mock()

    calculator.add_observer(observer1)
    calculator.add_observer(observer2)

    calculation = Mock(spec=Calculation)

    calculator.notify_observers(calculation)

    observer1.update.assert_called_once_with(calculation)
    observer2.update.assert_called_once_with(calculation)


def test_perform_operation_trims_history(calculator):
    calculator.config.max_history_size = 1

    operation = OperationFactory.create_operation("add")
    calculator.set_operation(operation)

    calculator.perform_operation(1, 2)
    calculator.perform_operation(3, 4)

    assert len(calculator.history) == 1
    assert calculator.history[0].result == Decimal("7")


def test_perform_operation_clears_redo_stack(calculator):
    calculator.redo_stack.append(Mock())

    operation = OperationFactory.create_operation("add")
    calculator.set_operation(operation)

    calculator.perform_operation(2, 3)

    assert calculator.redo_stack == []


def test_perform_operation_unexpected_exception(calculator):
    operation = Mock()
    operation.execute.side_effect = RuntimeError("boom")

    calculator.set_operation(operation)

    with pytest.raises(OperationError, match="Operation failed: boom"):
        calculator.perform_operation(2, 3)

def test_save_empty_history(calculator):
    calculator.history = []

    with patch("app.calculator.pd.DataFrame.to_csv") as mock_to_csv:
        calculator.save_history()
        mock_to_csv.assert_called_once()


def test_load_history_empty_file(calculator):
    with patch.object(Path, "exists", return_value=True), \
         patch("app.calculator.pd.read_csv") as mock_read_csv:

        mock_read_csv.return_value = pd.DataFrame()

        calculator.load_history()

        assert calculator.history == []


def test_load_history_file_does_not_exist(calculator):
    with patch.object(Path, "exists", return_value=False):
        calculator.load_history()

        assert calculator.history == []


def test_load_history_failure(calculator):
    with patch.object(Path, "exists", return_value=True), \
         patch("app.calculator.pd.read_csv",
               side_effect=Exception("read failed")):

        with pytest.raises(
            OperationError,
            match="Failed to load history: read failed"
        ):
            calculator.load_history()


def test_get_history_dataframe(calculator):
    operation = OperationFactory.create_operation("add")
    calculator.set_operation(operation)
    calculator.perform_operation(2, 3)

    df = calculator.get_history_dataframe()

    assert len(df) == 1
    assert df.iloc[0]["operation"] == "Addition"
    assert df.iloc[0]["operand1"] == "2"
    assert df.iloc[0]["operand2"] == "3"
    assert df.iloc[0]["result"] == "5"


def test_show_history(calculator):
    operation = OperationFactory.create_operation("add")
    calculator.set_operation(operation)
    calculator.perform_operation(2, 3)

    history = calculator.show_history()

    assert history == ["Addition(2, 3) = 5"]


def test_undo_when_empty(calculator):
    calculator.undo_stack = []

    assert calculator.undo() is False


def test_redo_when_empty(calculator):
    calculator.redo_stack = []

    assert calculator.redo() is False

def test_save_history_failure(calculator):
    with patch(
        "app.calculator.pd.DataFrame.to_csv",
        side_effect=Exception("save failed")
    ):
        with pytest.raises(
            OperationError,
            match="Failed to save history: save failed"
        ):
            calculator.save_history()

def test_repl_history_empty(monkeypatch, capsys):
    inputs = iter(["history", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    with patch(
        "app.calculator_repl.Calculator.load_history",
        return_value=None
    ):
        calculator_repl()

    output = capsys.readouterr().out
    assert "No calculations in history" in output


def test_repl_history_with_entry(monkeypatch, capsys):
    inputs = iter(["add", "2", "3", "history", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    calculator_repl()

    output = capsys.readouterr().out
    assert "Calculation History:" in output
    assert "1. Addition(2, 3) = 5" in output


def test_repl_clear(monkeypatch, capsys):
    inputs = iter(["clear", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    calculator_repl()

    output = capsys.readouterr().out
    assert "History cleared" in output


def test_repl_undo_nothing(monkeypatch, capsys):
    inputs = iter(["undo", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    calculator_repl()

    output = capsys.readouterr().out
    assert "Nothing to undo" in output


def test_repl_undo_success(monkeypatch, capsys):
    inputs = iter(["add", "2", "3", "undo", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    calculator_repl()

    output = capsys.readouterr().out
    assert "Operation undone" in output


def test_repl_redo_nothing(monkeypatch, capsys):
    inputs = iter(["redo", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    calculator_repl()

    output = capsys.readouterr().out
    assert "Nothing to redo" in output


def test_repl_redo_success(monkeypatch, capsys):
    inputs = iter(["add", "2", "3", "undo", "redo", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    calculator_repl()

    output = capsys.readouterr().out
    assert "Operation redone" in output


def test_repl_save(monkeypatch, capsys):
    inputs = iter(["save", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    calculator_repl()

    output = capsys.readouterr().out
    assert "History saved successfully" in output


def test_repl_load(monkeypatch, capsys):
    inputs = iter(["load", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    calculator_repl()

    output = capsys.readouterr().out
    assert "History loaded successfully" in output

def test_repl_exit_save_failure(monkeypatch, capsys):
    inputs = iter(["exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    with patch(
        "app.calculator_repl.Calculator.save_history",
        side_effect=Exception("save failed")
    ):
        calculator_repl()

    output = capsys.readouterr().out
    assert "Warning: Could not save history: save failed" in output
    assert "Goodbye!" in output


def test_repl_save_failure(monkeypatch, capsys):
    inputs = iter(["save", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    with patch(
        "app.calculator_repl.Calculator.save_history",
        side_effect=Exception("save failed")
    ):
        calculator_repl()

    output = capsys.readouterr().out
    assert "Error saving history: save failed" in output


def test_repl_load_failure(monkeypatch, capsys):
    inputs = iter(["load", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    with patch(
        "app.calculator_repl.Calculator.load_history",
        side_effect=Exception("load failed")
    ):
        calculator_repl()

    output = capsys.readouterr().out
    assert "Error loading history: load failed" in output


def test_repl_cancel_first_number(monkeypatch, capsys):
    inputs = iter(["add", "cancel", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    calculator_repl()

    output = capsys.readouterr().out
    assert "Operation cancelled" in output


def test_repl_cancel_second_number(monkeypatch, capsys):
    inputs = iter(["add", "2", "cancel", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    calculator_repl()

    output = capsys.readouterr().out
    assert "Operation cancelled" in output


def test_repl_unknown_command(monkeypatch, capsys):
    inputs = iter(["banana", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    calculator_repl()

    output = capsys.readouterr().out
    assert "Unknown command: 'banana'" in output 

def test_repl_operation_error(monkeypatch, capsys):
    inputs = iter(["divide", "10", "0", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    calculator_repl()

    output = capsys.readouterr().out
    assert "Error:" in output


def test_repl_unexpected_operation_error(monkeypatch, capsys):
    inputs = iter(["add", "2", "3", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    with patch(
        "app.calculator_repl.OperationFactory.create_operation",
        side_effect=RuntimeError("unexpected failure")
    ):
        calculator_repl()

    output = capsys.readouterr().out
    assert "Unexpected error: unexpected failure" in output


def test_repl_keyboard_interrupt(monkeypatch, capsys):
    calls = iter([KeyboardInterrupt(), "exit"])

    def mock_input(_):
        value = next(calls)
        if isinstance(value, BaseException):
            raise value
        return value

    monkeypatch.setattr("builtins.input", mock_input)

    calculator_repl()

    output = capsys.readouterr().out
    assert "Operation cancelled" in output


def test_repl_eof_error(monkeypatch, capsys):
    def mock_input(_):
        raise EOFError

    monkeypatch.setattr("builtins.input", mock_input)

    calculator_repl()

    output = capsys.readouterr().out
    assert "Input terminated. Exiting..." in output


def test_repl_command_loop_exception(monkeypatch, capsys):
    calls = iter([RuntimeError("command failure"), "exit"])

    def mock_input(_):
        value = next(calls)
        if isinstance(value, BaseException):
            raise value
        return value

    monkeypatch.setattr("builtins.input", mock_input)

    calculator_repl()

    output = capsys.readouterr().out
    assert "Error: command failure" in output


def test_repl_fatal_initialization_error(capsys):
    with patch(
        "app.calculator_repl.Calculator",
        side_effect=RuntimeError("fatal failure")
    ):
        with pytest.raises(RuntimeError, match="fatal failure"):
            calculator_repl()

    output = capsys.readouterr().out
    assert "Fatal error: fatal failure" in output
           